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
                'GSM8K.jsonl', 'config.py']
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
        'subprocess.run(["bash", "-o", "pipefail", "-c", ais_bench_cmd], check=True)')
    patched = patched.replace(rate,
        'return "unavailable" if queries <= 0 else format(hits / queries, ".2%")')
    metrics_return = '    return query_tokens, query_tokens_external, hit_tokens, hit_tokens_external'
    if patched.count(metrics_return) != 1:
        raise ValueError('Unexpected metrics reader; inspect source')
    patched = patched.replace(metrics_return,
        '    import json, time\n'
        '    with open("metrics-snapshots.jsonl", "a") as snapshot:\n'
        '        snapshot.write(json.dumps({"time": time.time(), "query": query_tokens, '
        '"external_query": query_tokens_external, "hit": hit_tokens, '
        '"external_hit": hit_tokens_external}) + "\\n")\n' + metrics_return)
    destination.mkdir(parents=True)
    manifest = {}
    for name in required:
        shutil.copy2(source / name, destination / name)
        manifest[name] = {'source_sha256': hashlib.sha256((source / name).read_bytes()).hexdigest()}
    (destination / 'aisbench_test.py').write_text(patched, encoding='utf-8')
    for name in required:
        manifest[name]['copied_sha256'] = hashlib.sha256((destination / name).read_bytes()).hexdigest()
    (destination / 'source-manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    return manifest


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--destination', type=Path, required=True)
    args = parser.parse_args()
    prepare(args.source, args.destination)
