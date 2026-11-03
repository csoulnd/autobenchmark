"""Create an isolated, auditable copy of the verified AISBench wrapper."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil


def prepare(source, destination):
    if destination.exists():
        raise ValueError('Destination already exists; do not overwrite case evidence')
    source = source.resolve()
    required = ['aisbench_test.py', 'generate_dataset.py', 'data_picker.py',
                'default_api.py', 'save_file.py', 'cal_prefix_hit_rate.py',
                'GSM8K.jsonl', 'config.py', 'dataset_cache.py', 'log_format.py']
    for name in required:
        if not (source / name).is_file():
            raise ValueError('Missing tool source: ' + name)
    original = (source / 'aisbench_test.py').read_text(encoding='utf-8')
    needle = 'subprocess.run(ais_bench_cmd, shell=True, check=True)'
    if original.count(needle) != 5:
        raise ValueError('Unexpected wrapper revision; inspect subprocess call sites')
    rate = 'return "0.00%" if queries == 0 else format(hits / queries, ".2%")'
    if original.count(rate) != 1:
        raise ValueError('Unexpected metric formatting; inspect source')
    patched = original.replace(needle,
        '_benchmark_run(["bash", "-o", "pipefail", "-c", ais_bench_cmd], check=True)')
    patched = patched.replace(rate,
        'return "unavailable" if queries <= 0 else format(hits / queries, ".2%")')
    # Mark actual wrapper boundaries; do not infer warmup from elapsed time/log polling.
    hooks = [('[开始] 前缀数据集测试', 'warmup', 'doing'),
             ('[完成] 前缀数据集测试完成，结果保存在aisbench_result.csv', 'warmup', 'done'),
             ('[开始] 全量数据集测试', 'benchmark', 'doing'),
             ('[完成] 全量数据集测试完成，结果保存在aisbench_result.csv', 'benchmark', 'done')]
    for message, stage, status in hooks:
        marker = 'logging.info(f"'+message+'")'
        if marker not in patched:
            raise ValueError('Missing benchmark event hook: '+message)
        patched = patched.replace(marker, marker+'; _benchmark_event('+repr(stage)+', '+repr(status)+')')
    patched = ('import json as _event_json, os as _event_os\n'
        '_event_stage = None\n'
        'def _benchmark_event(stage, status):\n'
        '    global _event_stage\n'
        '    _event_stage = stage if status == "doing" else None\n'
        '    if _event_os.environ.get("BENCH_EVENT_ROOT"):\n'
        '        from task_events import emit\n'
        '        emit(_event_os.environ["BENCH_EVENT_ROOT"], stage, status, '
        '**_event_json.loads(_event_os.environ["BENCH_EVENT_CONTEXT"]))\n'
        'def _benchmark_run(*args, **kwargs):\n'
        '    try:\n'
        '        result = subprocess.run(*args, **kwargs)\n'
        '        from log_format import normalize_log\n'
        '        normalize_log("aisbench.log")\n'
        '        return result\n'
        '    except Exception:\n'
        '        if _event_stage:\n'
        '            _benchmark_event(_event_stage, "fail")\n'
        '        raise\n'+patched)
    metrics_return = '    return query_tokens, query_tokens_external, hit_tokens, hit_tokens_external'
    if patched.count(metrics_return) != 1:
        raise ValueError('Unexpected metrics reader; inspect source')
    patched = patched.replace(metrics_return,
        '    import json, time\n'
        '    with open("metrics-snapshots.jsonl", "a") as snapshot:\n'
        '        snapshot.write(json.dumps({"time": time.time(), "query": query_tokens, '
        '"external_query": query_tokens_external, "hit": hit_tokens, '
        '"external_hit": hit_tokens_external}) + "\\n")\n' + metrics_return)
    patched = 'import sys, os\nsys.path.append(' + repr(str(source)) + ')\nos.environ["BENCH_TOOL_SOURCE"] = ' + repr(str(source)) + '\n' + patched
    destination.mkdir(parents=True)
    manifest = {}
    for name in required:
        if name in ('aisbench_test.py', 'config.py'):
            shutil.copy2(source / name, destination / name)
        manifest[name] = {'source_sha256': hashlib.sha256((source / name).read_bytes()).hexdigest()}
    (destination / 'aisbench_test.py').write_text(patched, encoding='utf-8')
    for name in required:
        manifest[name]['copied_sha256'] = hashlib.sha256((destination / name if (destination / name).exists() else source / name).read_bytes()).hexdigest()
    (destination / 'source-manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    return manifest


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--destination', type=Path, required=True)
    args = parser.parse_args()
    prepare(args.source, args.destination)
