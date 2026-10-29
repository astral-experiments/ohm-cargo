"""Reopen retained finished trial and independent empty products through read-only mounts."""
from pathlib import Path
import hashlib,json,os,shutil,subprocess as sp,sys
R=Path(__file__).resolve().parent;sys.path.insert(0,str(R))
import local_study as w
from mechanics import digest,get,store
from member_archive import witness
def guest(dest,rep,kind):
 q=get(rep/'result.json');se=rep.parents[2].name;state=q['source_state']
 targets=q.get('targets')or get(w.REP/se/state/'A-cold/cold/result.json')['targets']
 assert os.geteuid()==1000 and Path('/').stat().st_uid==0
 m=Path('/proc/self/mountinfo').read_text().splitlines()
 for name in ('', 'products','shared'):
  f=str(w.V/name);matches=[l for l in m if l.split()[4]==f];assert len(matches)==1 and 'ro'in matches[0].split()[5].split(',')
 records={}
 for k,rel in targets.items():
  path=w.V/rel;data=path.read_bytes();h=digest(data);assert h==(q['files']if kind=='trial'else q['products'])[k]
  v=witness(path)['typed']if k.endswith('.rlib')else h;assert q['semantic'][k]==v
  records[k]=dict(sha256=h,bytes=len(data),semantic=v)
  into=R/'reopened/objects'/h
  if not into.exists():into.write_bytes(data)
  assert digest(into)==h
 outcome={}
 if se=='build':
  tool=w.V/'lint-caller';v=sp.run([tool],capture_output=True,env=w.env,timeout=30);assert v.returncode==0 and v.stdout==b'17 29 12\n'and not v.stderr and digest(tool)==q['oracle']['caller'];outcome=dict(caller=digest(tool),value=v.stdout.decode().strip())
  into=R/'reopened/objects'/digest(tool)
  if not into.exists():shutil.copyfile(tool,into)
 elif se=='serde':
  tool=w.V/targets['test'];v=sp.run([tool,'--list'],capture_output=True,env=w.env,timeout=30);n=sp.run([tool,'--test-threads=1'],capture_output=True,env=w.env,timeout=30)
  assert v.returncode==n.returncode==0 and digest(v.stdout)==q['oracle']['list_sha'] and b'3 passed; 0 failed'in n.stdout;outcome=dict(list=digest(v.stdout),passed=3)
 else:
  bad=w.V/'lint-witness/bad.rs';assert bad.is_file() and b'intentional_missing_lint_witness' in bad.read_bytes();outcome=dict(valid=(w.V/'lint-witness/valid.rmeta').stat().st_size,invalid=q['oracle']['code'])
 store(dest,dict(selection=se,state=state,kind=kind,files=records,oracle=outcome,original_result=digest(rep/'result.json'),all_views_read_only=True))
def inspect(sel,st,role,tag,kind):
 slot,rep=w.leaf(sel,st,role);train=w.leaf(sel,st,role[0]+'-trained')[0];base=w.leaf(sel,st,'A-cold')[0]
 layers=[slot/'upper',Path(w.L['old_common']),Path(w.L['old_lower'])]
 if kind=='trial':layers=[slot/'upper',train/'upper',base/'upper',*layers[1:]]
 shell='''set -eu
slot=$1; view=$2; train=$3; kind=$4; code=$5; receipt=$6; rep=$7; shift 7
chain=
for l in "$@";do mount --bind "$l" "$l";mount -o remount,bind,ro "$l"; if test -n "$chain";then chain=$chain:$l;else chain=$l;fi;done
mount -t overlay overlay -o "ro,lowerdir=$chain" "$view"
mount -o remount,ro,exec,nosuid,nodev "$view"
for k in products shared;do
 if test "$kind" = trial;then
  mount -t overlay overlay -o "ro,lowerdir=$slot/$k-upper:$train/$k" "$view/$k"
  mount -o remount,ro,exec,nosuid,nodev "$view/$k"
 else
  mount --bind "$slot/$k" "$view/$k";mount -o remount,ro,bind,exec,nosuid,nodev "$view/$k"
 fi
done
exec setpriv --reuid=1000 --regid=1000 --init-groups --no-new-privs --inh-caps=-all --ambient-caps=-all --bounding-set=-all -- taskset -c 8-11 /usr/bin/python3 -IB "$code" guest "$receipt" "$rep" "$kind"'''
 name='-'.join([sel,st,role,tag])+'.json';f=R/'reopened'/name
 sp.run(['sudo','-n','unshare','--mount','--propagation','private','--','/bin/sh','-ec',shell,'private',slot,w.V,train,kind,Path(__file__).resolve(),f,rep/tag,*layers],check=True,timeout=60)
 return name,digest(f)
def main():
 assert (R/'series.exit').is_file() and all((R/('score-'+s+'.exit')).is_file() for s in w.selections)
 parents=R/'reopened';parents.mkdir(mode=0o700);(parents/'objects').mkdir();rows={}
 for sel,code in get(R/'series-closure.json').items():
  if code:continue
  for source in ('original','older'):
   row=next(j for j in reversed(get(R/'protocol.json')['schedule'][sel])if j['from_state']==source)
   for a in 'AB':
    for what in ((w.other(source),a+'-cold','cold','cold'),(source,a+'-slot'+str(row['pair']).zfill(2),'measured','trial')):
     name,h=inspect(sel,*what);rows[name]=h
 store(parents/'complete.json',dict(rows=rows,objects={x.name:x.stat().st_size for x in sorted((parents/'objects').iterdir())},all_readonly=True));print('Reopened',len(rows),'representative live views',flush=True)
if __name__=='__main__':
 if len(sys.argv)>1:guest(Path(sys.argv[2]),Path(sys.argv[3]),sys.argv[4])
 else:main()
