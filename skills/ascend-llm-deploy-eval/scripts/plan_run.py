"""Validate a planning contract; never deploy or mark runtime checks passed."""
import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load_json(path):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError('Duplicate JSON key: ' + key)
            result[key] = value
        return result
    return json.loads(Path(path).read_text(encoding='utf-8-sig'), object_pairs_hook=pairs,
                      parse_constant=lambda x: (_ for _ in ()).throw(ValueError(x)))


def validate(spec):
    from jsonschema import Draft202012Validator
    schema = load_json(ROOT / 'schemas/job_spec.schema.json')
    errors = [f'{e.json_path}: {e.message}' for e in Draft202012Validator(schema).iter_errors(spec)]
    if errors:
        return errors
    instances = {x['role']: x for x in spec['instances']}
    if set(instances) != {'prefill', 'decode'}:
        return ['instances: require exactly one prefill and one decode']
    devices, ports, engines = set(), {spec['proxy']['port']}, set()
    for role, inst in instances.items():
        if len(inst['device_ids']) != inst['dp'] * inst['tp']:
            errors.append(role + ': device count must equal dp * tp')
        if devices.intersection(inst['device_ids']):
            errors.append('P/D device overlap')
        devices.update(inst['device_ids'])
        for field in ('port', 'dp_rpc_port', 'kv_port'):
            if inst[field] in ports:
                errors.append('port collision: ' + str(inst[field]))
            ports.add(inst[field])
        if inst['engine_id'] in engines:
            errors.append('duplicate engine_id')
        engines.add(inst['engine_id'])
        if spec['kv_transfer'][role] != {k: inst[k] for k in ('dp', 'tp')}:
            errors.append(role + ': KV topology mismatch')
    bench = spec['benchmark']
    if bench['prefill_dp'] != instances['prefill']['dp']:
        errors.append('warmup DP differs from prefill DP')
    ids = set()
    for case in bench['cases']:
        if case['id'] in ids:
            errors.append('duplicate case id: ' + case['id'])
        ids.add(case['id'])
        if case['input_tokens'] + case['output_tokens'] > spec['model']['max_model_len']:
            errors.append(case['id'] + ': context limit exceeded')
        if case['formal_requests'] < case['concurrency']:
            errors.append(case['id'] + ': requests cannot reach requested concurrency')
        if case['prefix_ratio'] > 0 and (not bench['prefix_caching'] or not case['warmup']):
            errors.append(case['id'] + ': prefix test requires cache and warmup')
    if spec['state'] == 'ready':
        for group, fields in [('target', ('host', 'container', 'work_dir', 'image_id')),
                              ('model', ('path',)), ('benchmark', ('tool_dir', 'aisbench_work_path'))]:
            for field in fields:
                if spec[group][field] is None:
                    errors.append(group + '.' + field + ': unresolved')
        if spec['unresolved']:
            errors.append('ready spec has unresolved items')
    return errors


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-dir', type=Path, required=True)
    parser.add_argument('--job-spec', type=Path)
    args = parser.parse_args()
    result = dict(stage='plan_run', status='BLOCKED', message='', artifacts=[])
    try:
        if not args.run_dir.is_absolute():
            raise ValueError('run-dir must be absolute')
        if args.job_spec is None:
            raise ValueError('--job-spec is required; no plan generated')
        spec = load_json(args.job_spec)
        errors = validate(spec)
        if errors:
            raise ValueError('; '.join(errors))
        if spec['state'] != 'ready':
            raise ValueError('Draft validated; resolve target and unresolved items before planning')
        canonical = json.dumps(spec, ensure_ascii=False, sort_keys=True, separators=(',', ':'))
        plan = dict(job_spec=spec, job_spec_sha256=hashlib.sha256(canonical.encode()).hexdigest(),
                    status='PLANNED', runtime_verified=False,
                    stages=['preflight', 'deploy', 'evaluate', 'finalize'])
        args.run_dir.mkdir(parents=True, exist_ok=True)
        output = args.run_dir / 'plan.json'
        with output.open('x', encoding='utf-8') as f:
            json.dump(plan, f, ensure_ascii=False, indent=2)
        result.update(status='PLANNED', message='Plan only; runtime stages remain unimplemented',
                      artifacts=[str(output)])
    except (ValueError, OSError, ImportError) as exc:
        result['message'] = str(exc)
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result['status'] == 'PLANNED' else 2


if __name__ == '__main__':
    raise SystemExit(main())
