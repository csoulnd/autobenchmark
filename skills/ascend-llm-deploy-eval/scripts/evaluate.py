"""One case at a time; attempt budgets and results are scoped by case ID."""
import json
from pathlib import Path
import shutil
import subprocess
import time
from deploy import deploy
from finalize import release
from prepare_benchmark_tool import prepare
from stage_runtime import (entry, read_plan, ready, save, service_identity, state,
                           transition, case_state, update_case)


def evaluate(root, case=None, finish_case=True):
    spec = read_plan(root)
    case = case or spec['benchmark']['case']
    case_id = case['id']
    data = case_state(root, case_id)
    if data['status'] == 'PASSED':
        from validate_case import validate
        folder = Path(data['attempts'][-1]['folder'])
        validate(folder, json.loads((folder/'case.json').read_text()))
        return {'status': 'PASSED', 'message': 'Completed case revalidated; no replay',
                'artifacts': [str(folder/'validated.json')]}
    if data['status'] == 'RUNNING':
        raise ValueError('Interrupted case has unknown client state; cleanup required')
    if not ready(root, spec):
        deploy(root)
    for name in ['case_runner.py', 'service_process.py', 'validate_case.py', 'cache_reset.py']:
        shutil.copy2(Path(__file__).with_name(name), root/'scripts'/name)
    limit = 1 + spec['execution']['max_retries']
    for attempt in range(len(data['attempts']) + 1, limit + 1):
        if not ready(root, spec):
            raise ValueError('Service not READY; no blind case replay')
        folder = root/'results'/case_id/f'attempt-{attempt:02}'
        folder.mkdir(parents=True, exist_ok=False)
        save(folder/'case.json', case)
        item = {'attempt': attempt, 'folder': str(folder), 'status': 'RUNNING', 'stage': 'evaluate'}
        attempts = case_state(root, case_id)['attempts'] + [item]
        update_case(root, case_id, status='RUNNING', attempts=attempts, safe_to_continue=False)
        identity = service_identity(spec, root)
        transition(root, 'TESTING', cache_state='DIRTY')
        error = None
        try:
            prepare(Path(spec['benchmark']['tool_dir']), folder/'tool')
            with (folder/'runner.log').open('w') as log:
                result = subprocess.run(['docker', 'exec', state(root)['container_id'],
                    'python3', str(root/'scripts/case_runner.py'), str(root), str(folder)],
                    stdout=log, stderr=subprocess.STDOUT)
            returncode = result.returncode
        except Exception as exc:
            returncode = 2
            error = repr(exc)
        cleanup = json.loads((folder/'cleanup.json').read_text()) if (folder/'cleanup.json').exists() else {'released': False, 'error': 'No cleanup evidence'}
        summary = json.loads((folder/'summary.json').read_text()) if (folder/'summary.json').exists() else {'status': 'FAILED', 'error': error or 'Runner failed; see runner.log'}
        passed = returncode == 0 and summary['status'] == 'PASSED' and cleanup['released']
        try:
            unchanged = identity == service_identity(spec, root)
        except Exception:
            unchanged = False
        safe = bool(cleanup['released'] and unchanged)
        item.update(status='PASSED' if passed else 'FAILED', returncode=returncode,
                    summary=summary, cleanup=cleanup)
        attempts[-1] = item
        update_case(root, case_id, status=item['status'], attempts=attempts, safe_to_continue=safe)
        transition(root, 'READY' if unchanged else 'UNKNOWN', cache_state='NEEDS_RESET')
        if passed:
            if finish_case:
                release(root, spec['cleanup']['after_case'], 'case')
            return {'status': 'PASSED', 'message': f'{case_id} passed on attempt {attempt}',
                    'artifacts': [str(folder/'validated.json')]}
        if not safe or not case.get('reset_cache', True):
            raise ValueError('Unsafe to retry: client/service/cache isolation not verified')
        print(json.dumps({'event': 'case_attempt_failed', 'case_id': case_id,
                          'attempt': attempt, 'max_attempts': limit, 'error': summary.get('error')}), flush=True)
        if attempt < limit:
            time.sleep(3)
    if finish_case:
        release(root, spec['cleanup']['after_case'], 'case')
    raise RuntimeError('Case exhausted retry budget; evidence retained')


if __name__ == '__main__':
    raise SystemExit(entry('evaluate', evaluate))
