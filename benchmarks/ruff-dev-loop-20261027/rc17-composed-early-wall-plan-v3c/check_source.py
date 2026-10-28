"""Match checked PR Git trees to the exact source blobs/modes used for each measured Cargo."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys

HERE=Path(__file__).resolve().parent
P=json.loads((HERE/'plan.json').read_bytes())
def verify(repo,qa):
    commit=P['composed_ci'];out={}
    def git(*args):
        return subprocess.check_output(['git','--no-optional-locks','-C',repo,*args])
    for arm,role in [('B','observer'),('C','composed')]:
        expected=commit[role];head=expected['head']
        root=git('rev-parse',head+'^{tree}').decode().strip()
        assert root==expected['tree']
        parents=git('show','-s','--format=%P',head).decode().split()
        assert parents==expected['parents']
        rows=[]
        for line in git('ls-tree','-rz',head).split(b'\0'):
            if not line:continue
            meta,name=line.split(b'\t',1);mode,typ,oid=meta.decode().split()
            assert typ=='blob' and mode in ('100644','100755','120000')
            rows.append([name.decode(),mode,oid])
        h=hashlib.sha256((json.dumps(rows,sort_keys=True,separators=(',',':'))+'\n').encode()).hexdigest()
        previous=json.loads((qa/('build-original.json' if arm=='B' else 'build-composed.json')).read_bytes())['physical']
        assert previous['source_records_sha256']==expected['physical_source_sha256']==h
        assert previous['files']==len(rows)==3108 and previous['cargo']==P['subject_images'][arm]
        out[arm]={'commit':head,'tree':root,'parents':parents,'source_files_and_modes':len(rows),
                  'build_source_sha256':h,'binary_sha256':previous['cargo']}
    diff=git('diff','--name-only',commit['observer']['head'],commit['composed']['head']).decode().splitlines()
    assert diff==commit['scheduler_files'] and len(diff)==3
    return {'subjects':out,'scheduler_files':diff,'historical_component':P['source']['guard']}
if __name__=='__main__':print(json.dumps(verify(Path(sys.argv[1]),Path(sys.argv[2])),indent=2,sort_keys=True))
