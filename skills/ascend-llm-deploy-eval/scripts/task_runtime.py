"""Serial task control. Configuration storage is an event hook, not a catalog."""
from datetime import datetime, timezone
import json
from pathlib import Path
from stage_runtime import (digest, save, locked, record, state, case_state)


def storage_event(root, event, **fields):
    path = root/'logs/config-storage-events.jsonl'
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('a', encoding='utf-8') as stream:
        stream.write(json.dumps({'time': datetime.now(timezone.utc).isoformat(),
            'event': event, 'storage': 'not_implemented', **fields})+'\n')


def read_task(root):
    plan = json.loads((root/'plan.json').read_text(encoding='utf-8-sig'))
    spec = plan['job_spec']
    if spec['schema_version'] != '3.0' or digest(spec) != plan['job_spec_sha256']:
        raise ValueError('Invalid task plan or hash')
    expected = [{'case_id': c['id'], 'deployment_id': c['deployment_id']} for c in spec['cases']]
    if plan.get('sequence') != expected:
        raise ValueError('Execution sequence differs from frozen cases')
    return spec


def validate_task(spec):
    errors = []
    deployments = {d['id']: d for d in spec['deployments']}
    if len(deployments) != len(spec['deployments']):
        errors.append('Duplicate deployment ID')
    seen = set()
    for dep in deployments.values():
        names = [c['name'] for c in dep['commands']]
        if len(names) != len(set(names)):
            errors.append('Duplicate command name in '+dep['id'])
    for case in spec['cases']:
        if case['id'] in seen:
            errors.append('Duplicate case ID')
        seen.add(case['id'])
        dep = deployments.get(case['deployment_id'])
        if dep is None:
            errors.append('Unknown deployment for '+case['id'])
            continue
        if case['input_tokens'] + case['output_tokens'] > dep['model']['max_model_len']:
            errors.append('Context limit exceeded: '+case['id'])
        if case.get('formal_requests', case['concurrency']*4) < case['concurrency']:
            errors.append('Requests cannot reach concurrency: '+case['id'])
    if spec['state'] == 'ready' and spec['unresolved']:
        errors.append('Ready task has unresolved items')
    return errors


def resolved_task(root):
    spec = read_task(root)
    path = root/'resolved-task.json'
    if not path.exists():
        raise ValueError('Run attended preflight before starting task')
    resolved = json.loads(path.read_text())
    if resolved['plan_sha256'] != digest(spec) or resolved['run_dir'] != str(root.resolve()):
        raise ValueError('Preflight bindings do not match this task/location')
    for item in resolved['deployments'].values():
        child = Path(item['run_dir'])
        if not child.resolve().is_relative_to(root.resolve()):
            raise ValueError('Resolved deployment outside task root')
        execution = json.loads((child/'resolved.json').read_text())
        if digest(execution) != item['execution_sha256']:
            raise ValueError('Resolved deployment changed after preflight')
        # Detect changes to rendered startup scripts too.
        for name, expected in item['scripts_sha256'].items():
            import hashlib
            if hashlib.sha256((child/'scripts'/name).read_bytes()).hexdigest() != expected:
                raise ValueError('Startup script changed after preflight: '+name)
    return spec, resolved


def invoke(root, stage, operation):
    captured = {}
    def execute():
        try:
            result = operation()
        except Exception as exc:
            result = {'status': 'FAILED', 'message': repr(exc), 'artifacts': []}
        captured.update(result)
        return result
    record(root, stage, execute)
    return captured


def finalize_case(root, case, policy):
    from finalize import release
    from stage_runtime import update
    data = case_state(root, case['id'])
    attempts = data['attempts']
    if data['status'] == 'RUNNING' or (attempts and not attempts[-1].get('cleanup', {}).get('released')):
        raise ValueError('Case client cleanup is unverified; task cleanup required')
    # The next evaluate must reset before warmup. No redundant reset after stop.
    update(root, cache_state='NEEDS_RESET')
    release(root, policy, 'case:'+case['id'])
    return {'status': 'PASSED', 'message': 'Case temporary resources verified; service policy applied',
            'artifacts': []}


def finalize_task(root):
    spec, resolved = resolved_task(root)
    from finalize import release
    failures, releases = [], {}
    for dep_id, item in resolved['deployments'].items():
        child = Path(item['run_dir'])
        try:
            with locked(json.loads((child/'resolved.json').read_text())):
                releases[dep_id] = release(child, spec['cleanup']['task_end'], 'job')
        except Exception as exc:
            failures.append({'deployment_id': dep_id, 'error': repr(exc)})
    task_state = json.loads((root/'task-state.json').read_text()) if (root/'task-state.json').exists() else {'cases': {}}
    cases = {c['id']: task_state['cases'].get(c['id'], {
        'status': 'NOT_RUN', 'deployment_id': c['deployment_id']}) for c in spec['cases']}
    all_passed = all(cases.get(c['id'], {}).get('status') == 'PASSED' for c in spec['cases'])
    summary = {'job_id': spec['job_id'], 'evaluation_status': 'PASSED' if all_passed else 'FAILED',
               'cases': cases, 'releases': releases, 'release_failures': failures,
               'release_status': 'FAILED' if failures else 'PASSED'}
    save(root/'summary.json', summary)
    return {'status': 'FAILED' if failures else 'PASSED', 'message': 'Task cleanup verified' if not failures else 'Task cleanup needs attention',
            'artifacts': [str(root/'summary.json')]}


def run_task(root):
    spec, resolved = resolved_task(root)
    from deploy import deploy
    from evaluate import evaluate
    path = root/'task-state.json'
    task_state = json.loads(path.read_text()) if path.exists() else {'cases': {}}
    # An interrupted loop is not silently resumed; explicit cleanup is available.
    if any(c.get('status') == 'RUNNING' for c in task_state['cases'].values()):
        raise ValueError('Interrupted task has unknown client state; run finalize first')
    failed = False
    cleanup = None
    try:
        for index, case in enumerate(spec['cases']):
            if task_state['cases'].get(case['id'], {}).get('status') in ['PASSED', 'FAILED']:
                failed |= task_state['cases'][case['id']]['status'] == 'FAILED'
                continue
            dep_id = case['deployment_id']
            child = Path(resolved['deployments'][dep_id]['run_dir'])
            execution = json.loads((child/'resolved.json').read_text())
            task_state['cases'][case['id']] = {'status': 'RUNNING', 'deployment_id': dep_id}
            save(path, task_state)
            with locked(execution):
                deployment = invoke(child, 'deploy', lambda: deploy(child))
                if deployment['status'] == 'PASSED':
                    storage_event(root, 'deployment_verified', deployment_id=dep_id,
                                  service_fingerprint=execution['service_fingerprint'])
                    result = invoke(child, 'evaluate', lambda: evaluate(child, case, finish_case=False))
                else:
                    result = deployment
                outcome = {'status': result['status'], 'deployment_id': dep_id, 'result': result}
                task_state['cases'][case['id']] = outcome
                save(path, task_state)
                next_dep = spec['cases'][index+1]['deployment_id'] if index+1 < len(spec['cases']) else None
                # A changed deployment gets a fresh container namespace. Same-deployment
                # cases retain the existing service unless explicitly configured otherwise.
                policy = 'stop_container' if next_dep and next_dep != dep_id else spec['cleanup']['after_case']
                finish = invoke(child, 'finalize', lambda: finalize_case(child, case, policy))
                outcome['finalize'] = finish
                save(path, task_state)
                storage_event(root, 'case_finished', case_id=case['id'], deployment_id=dep_id, status=result['status'])
                if finish['status'] != 'PASSED':
                    failed = True
                    break
                if result['status'] != 'PASSED':
                    failed = True
                    current = case_state(child, case['id'])
                    if state(child)['service'] != 'RELEASED' and not current.get('safe_to_continue', False):
                        break
    finally:
        cleanup = invoke(root, 'finalize', lambda: finalize_task(root))
    summary = json.loads((root/'summary.json').read_text())
    passed = not failed and summary['evaluation_status'] == 'PASSED' and cleanup['status'] == 'PASSED'
    return {'status': 'PASSED' if passed else 'FAILED', 'message': 'Serial task finished; inspect per-case results and cleanup',
            'artifacts': [str(root/'summary.json')]}


def stage_entry(stage, root, bindings=None):
    spec = read_task(root)
    with locked({'target': {'container': spec['job_id']}}):
        if stage == 'preflight':
            from task_preflight import prepare_task
            return prepare_task(root, bindings or root/'bindings.json')
        if stage == 'evaluate':
            return run_task(root)
        if stage == 'finalize':
            return finalize_task(root)
        raise ValueError('Use generated run.sh to execute deploy/test/finalize in task order')
