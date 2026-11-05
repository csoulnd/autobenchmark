"""Diagnostic-only native worker RPC: hash active expert bytes while frozen."""
import os
import ctypes
import hashlib
import json
from pathlib import Path
import time

import torch
import torch_npu
from vllm.distributed import get_ep_group

_ROOT = Path(os.environ['EPLB_OUTPUT_DIR'])


class EplbRealHashExtension:
    def dsv41_eplb_realhash(self, action: str, label: str = ''):
        controller = self.model_runner.eplb
        assert controller.state is not None, 'EPLB must be enabled'
        rank = get_ep_group().rank_in_group
        if action == 'freeze':
            controller.suppressed = True
        elif action == 'resume':
            controller.suppressed = False
        elif action not in ('status', 'snapshot'):
            raise ValueError(action)
        summary = {'rank': rank, 'suppressed': controller.suppressed,
                   'models': {str(k): {'layers': m.model.num_moe_layers,
                                     'rebalanced': bool(m.rebalanced),
                                     'pending_layer': getattr(m.pending_result, 'layer_idx', None)}
                              for k, m in controller.state.model_states.items()}}
        if action != 'snapshot':
            return summary
        assert controller.suppressed
        assert label in ('before', 'after'), label
        output = _ROOT / f'eplb-realhash-{label}-rank{rank}.jsonl'
        assert not output.exists(), output
        torch.npu.synchronize()
        lib = ctypes.CDLL('libascendcl.so')
        lib.aclrtMemcpy.argtypes = [ctypes.c_void_p, ctypes.c_size_t,
                                   ctypes.c_void_p, ctypes.c_size_t, ctypes.c_int]
        lib.aclrtMemcpy.restype = ctypes.c_int
        start = time.monotonic()
        rows = total_bytes = 0
        buffer = None
        buffer_size = 0
        with output.open('x') as f:
            f.write(json.dumps({'type': 'header', **summary}) + '\n')
            for key, state in controller.state.model_states.items():
                mapping = state.physical_to_logical_map.cpu().tolist()
                logical_map = state.logical_to_physical_map.cpu().tolist()
                replicas = state.logical_replica_count.cpu().tolist()
                layers = list(state.model.moe_layers)
                f.write(json.dumps({'type': 'mapping', 'model': str(key),
                                    'physical_to_logical': mapping,
                                    'logical_to_physical': logical_map,
                                    'replica_count': replicas}) + '\n')
                for layer in range(state.model.num_moe_layers):
                    weights = state.model.expert_weights[layer]
                    local_count = len(weights[0])
                    assert len(mapping[layer]) == local_count * get_ep_group().world_size
                    route_state = layers[layer].eplb_state
                    route = route_state.expert_replica_routing_table
                    f.write(json.dumps({'type': 'route', 'model': str(key),
                                        'layer': layer, 'table': route.cpu().tolist()}) + '\n')
                    for param, view in enumerate(weights):
                        assert len(view) == local_count
                        for slot in range(local_count):
                            tensor = view[slot]
                            size = tensor.nbytes
                            if size > buffer_size:
                                buffer = ctypes.create_string_buffer(size)
                                buffer_size = size
                            rc = lib.aclrtMemcpy(buffer, size, tensor.data_ptr(), size, 2)
                            assert rc == 0, (rank, layer, param, slot, rc)
                            digest = hashlib.sha256(memoryview(buffer).cast('B')[:size]).hexdigest()
                            physical = rank * local_count + slot
                            record = {'type': 'weight', 'model': str(key), 'layer': layer,
                                      'param': param, 'physical': physical,
                                      'logical': mapping[layer][physical], 'sha256': digest,
                                      'bytes': size, 'dtype': str(tensor.dtype),
                                      'shape': list(tensor.shape), 'stride': list(tensor.stride()),
                                      'format': torch_npu.get_npu_format(tensor)}
                            f.write(json.dumps(record) + '\n')
                            rows += 1
                            total_bytes += size
                    f.flush()
                    if (layer + 1) % 10 == 0:
                        print('EPLB_REALHASH_PROGRESS', label, rank, layer + 1,
                              rows, total_bytes, flush=True)
            result = {'type': 'complete', 'rank': rank, 'rows': rows,
                      'bytes': total_bytes, 'seconds': time.monotonic() - start}
            f.write(json.dumps(result) + '\n')
        print('EPLB_REALHASH_COMPLETED', label, result, flush=True)
        return {**result, 'path': str(output)}
