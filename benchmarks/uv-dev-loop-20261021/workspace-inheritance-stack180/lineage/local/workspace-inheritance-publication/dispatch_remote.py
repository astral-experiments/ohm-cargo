
import json,subprocess,datetime,os,socket
from pathlib import Path
root=Path('/tmp/ohm-hillclimb-20261021-inheritance-code-publication');assert root.resolve()==root and root.stat().st_uid==os.getuid()==1000 and socket.gethostname()=='charlie-oss-5'
publication=json.loads((root/'publication.json').read_text());repo='astral-sh/ohm-cargo';branch=publication['branch'];commit=publication['commit']
head=json.loads(subprocess.check_output(['gh','api','repos/'+repo+'/git/ref/heads/'+branch]));assert head['object']['sha']==commit
assert not (root/'ci-dispatch.json').exists()
existing=json.loads(subprocess.check_output(['gh','run','list','--repo',repo,'--workflow','ci.yml','--branch',branch,'--event','workflow_dispatch','--limit','5','--json','headSha,status,conclusion,databaseId,url,createdAt,workflowName']))
assert not [row for row in existing if row['headSha']==commit], 'Exact source already has a dispatched CI run'
started=datetime.datetime.now(datetime.timezone.utc).isoformat()
r=subprocess.run(['gh','workflow','run','ci.yml','--repo',repo,'--ref',branch],capture_output=True,text=True)
record={'started_at':started,'finished_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'workflow':'ci.yml','branch':branch,'commit':commit,'optional_clippy_apfs_replay':False,'returncode':r.returncode,'stdout':r.stdout,'stderr':r.stderr}
(root/'ci-dispatch.json').write_text(json.dumps(record,indent=2)+'\n')
assert r.returncode==0,record
runs=json.loads(subprocess.check_output(['gh','run','list','--repo',repo,'--workflow','ci.yml','--branch',branch,'--event','workflow_dispatch','--limit','5','--json','headSha,status,conclusion,databaseId,url,createdAt,workflowName']))
record['runs']=[x for x in runs if x['headSha']==commit]
(root/'ci-dispatch-observed.json').write_text(json.dumps(record,indent=2)+'\n');print(json.dumps(record))
