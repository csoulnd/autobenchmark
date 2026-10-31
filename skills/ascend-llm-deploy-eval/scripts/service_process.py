"""Container-side owned process groups; PID plus start-time prevents PID reuse."""
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time


def ticks(pid):
    try:
        fields=Path(f'/proc/{pid}/stat').read_text().split(') ',1)[1].split()
        return None if fields[0]=='Z' else fields[19]
    except FileNotFoundError:
        return None


def members(pgid):
    found=[]
    for path in Path('/proc').glob('[0-9]*/stat'):
        try:
            fields=path.read_text().split(') ',1)[1].split()
            if fields[0]!='Z' and int(fields[2])==pgid: found.append(int(path.parent.name))
        except (FileNotFoundError,ProcessLookupError): pass
    return found


def main(action,root):
    path=root/'service-processes.json'
    data=json.loads(path.read_text()) if path.exists() else []
    if action=='start':
        if data: raise ValueError('Existing service process registry; stop before start')
        service=json.loads((root/'scripts/service.json').read_text())
        for item in service['commands']:
            with (root/'logs'/(item['name']+'.log')).open('a') as log:
                proc=subprocess.Popen(item['argv'],stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
            data.append({'name':item['name'],'pid':proc.pid,'start_ticks':ticks(proc.pid)})
            path.write_text(json.dumps(data,indent=2))
    elif action=='identity':
        if not data or any(ticks(x['pid'])!=x['start_ticks'] or x['start_ticks'] is None for x in data):
            raise ValueError('Service process missing or identity changed')
    elif action=='stop':
        for item in reversed(data):
            pid=item['pid']; current=ticks(pid)
            if current is not None and current!=item['start_ticks']:
                raise ValueError('PID ownership changed; refuse kill')
            if members(pid):
                os.killpg(pid,signal.SIGTERM)
                deadline=time.monotonic()+20
                while members(pid) and time.monotonic()<deadline: time.sleep(.2)
                if members(pid): os.killpg(pid,signal.SIGKILL)
                deadline=time.monotonic()+10
                while members(pid) and time.monotonic()<deadline: time.sleep(.2)
                if members(pid): raise RuntimeError('Owned process group remains')
        path.write_text('[]')
        data={'released':True}
    else: raise ValueError('Unknown process action')
    print(json.dumps(data))

if __name__=='__main__': main(sys.argv[1],Path(sys.argv[2]))
