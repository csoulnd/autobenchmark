"""Render real per-node files using mocked discovery, without Docker or SSH."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'skills/ascend-llm-deploy-eval/scripts'))
import cluster_runtime as cluster
import node_prepare
import plan_run
from test_serial_task import fixture


class NodePreparationTests(unittest.TestCase):
    def test_two_nodes_render_cross_host_routes_and_detect_changed_request(self):
        spec=plan_run.normalize(fixture());spec['deployments']=spec['deployments'][:1]
        dep=spec['deployments'][0]
        dep['instances'][1]['placement']['node']='b'
        calls=[]
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);model=root/'model';model.mkdir()
            bindings={'nodes':{key:{'host':key+'.example','work_dir':str(root/key),'package':'/skill',
                'model_paths':{'m':str(model)},'paths':{'comm':'/etc/hixlep'}} for key in ['a','b']}}
            def rpc(binding,request):
                calls.append(request)
                host=binding['host']
                with patch.object(node_prepare,'discover_network',return_value={'interface':'nic','ip':'192.0.2.1' if host.startswith('a') else '192.0.2.2'}), \
                     patch.object(node_prepare,'command',side_effect=lambda argv:json.dumps([{'Id':'image-sha'}]) if argv[0]=='docker' else 'idle'), \
                     patch.object(node_prepare,'inspect_image_tools',return_value={'aisbench_work_path':'/ais'}), \
                     patch('preflight.check',return_value={'status':'PASSED'}):
                    return node_prepare.prepare(request)
            with patch.object(cluster,'prepare_call',side_effect=rpc):
                cluster.preflight(root,spec,bindings)
            resolved=json.loads((root/'resolved-cluster.json').read_text())['deployments']['a']
            self.assertEqual(len(resolved['groups']),2)
            group=Path(resolved['groups']['a/model']['run_dir'])
            proxy=(group/'scripts/start-proxy.sh').read_text()
            self.assertIn('192.0.2.2',proxy)
            self.assertNotIn('{{',proxy)
            service=json.loads((group/'scripts/service.json').read_text())
            self.assertIn('192.0.2.2',service['reset_urls'][1])
            changed=next(r for r in calls if r['action']=='render')
            changed['deployment']['commands'][0]['env']['CHANGED']='1'
            with self.assertRaises(ValueError):node_prepare.prepare(changed)

    def test_unregistered_directory_is_not_overwritten(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);(root/'unrelated.txt').write_text('preserve')
            with self.assertRaises(ValueError):node_prepare.prepare({'run_dir':str(root),'job_id':'20261101-123','action':'discover'})
            self.assertEqual((root/'unrelated.txt').read_text(),'preserve')
