"""Native and wall driver for genuine first transitions of an active Ruff workspace lint."""
from pathlib import Path
import hashlib,json,os,re,shutil,signal,socket,stat,statistics,subprocess as sp,sys,time
ROOT=Path(__file__).resolve().parent;sys.path.insert(0,str(ROOT))
from mechanics import digest,get,store,sound_timing,scan_exec,inventory
from member_archive import witness
L=get(ROOT/'layout.json');S=get(ROOT/'source.json');srcfiles=get(ROOT/'source-files.json')
V=Path(L['view']);SRC=V/'source';PH=Path(L['allocation']);REP=ROOT/'runs';LOCK=SRC/'Cargo.lock';MAN=SRC/'Cargo.toml';MRK=V/'products/.cargo-resolve-cache-v1';env=get(Path(L['prior_enrollment']))['env']
proxy=Path(env['HOME'])/'.cargo/bin/cargo';rust=proxy.parent/'rustc'
selections={'check':['check','-p','ruff_text_size'],'build':['build','-p','ruff_text_size'],'serde':['test','-p','ruff_text_size','--features','serde','--test','serde','--no-run']}
def disk(): 
 out=[shutil.disk_usage(f).free for f in (Path(env['HOME']),ROOT,PH.parent)];assert min(out[:2])>24*2**30 and out[2]>16*2**30,out;return out
def amark():return digest(MRK)if MRK.exists()else None
def other(state):return 'older'if state=='original'else'original'
def text(state):
 base=MAN.read_bytes();needle=S['added_on_reverse'].encode();anchor=S['anchor'].encode();assert base.count(anchor)==1
 a=base.replace(needle,b'');e=a.replace(anchor,needle+anchor);assert digest(a)==S['source_manifest'] and digest(e)==S['reverse_manifest'];return a if state=='original'else e
def putstate(state):
 d=text(state)
 if MAN.read_bytes()!=d:MAN.write_bytes(d)
 assert digest(MAN)==(S['source_manifest']if state=='original'else S['reverse_manifest'])
def native(d,sel,state,argv):
 with (d/'stdout').open('xb')as o,(d/'stderr').open('xb')as e:
  r=sp.run(['strace','-ff','-qq','-s','131072','-e','trace=process','-o',str(d/'kernel'),*argv,'--message-format=json'],cwd=SRC,env=env,stdin=sp.DEVNULL,stdout=o,stderr=e,timeout=240)
 assert r.returncode==0,(sel,state,(d/'stderr').read_bytes()[-700:])
 stream=[json.loads(x)for x in (d/'stdout').read_bytes().splitlines()];assert stream[-1]=={'reason':'build-finished','success':True};arts=[a for a in stream if a['reason']=='compiler-artifact'];assert arts
 rows=[];refs={};targets={};products={};semantic={};fresh=[]
 for a in arts:
  tid=[a['package_id'],a['target']['name'],a['target']['kind'],a['features']];rows.append(tid);fresh.append(a['fresh'])
  for name in a['filenames']:
   f=Path(name);rel=str(f.relative_to(V));val=digest(f);refs[rel]=val
   if '/crates/ruff_text_size#' not in a['package_id']:continue
   c='library'if a['target']['kind']==['lib'] else 'test'if a['target']['kind']==['test']else None;assert c
   key=c+(f.suffix if c=='library'else'');targets[key]=rel;products[key]=val
   if f.suffix=='.rlib':
    detail=witness(f);semantic[key]=detail['typed'];store(d/'root-archive.json',detail)
   else:semantic[key]=val
  if a['executable']:
   assert a['target']['kind']==['test']and targets['test']==str(Path(a['executable']).relative_to(V))
 assert products and (set(products)=={'library.rmeta'}if sel=='check'else set(products)=={'library.rlib','library.rmeta'}if sel=='build'else set(products)=={'library.rlib','library.rmeta','test'}),(sel,targets)
 streams,execs=scan_exec(d);comps=[];links=[];script=[]
 for pid,path,av in execs:
  n=Path(path).name
  if n=='rustc'and '--crate-name'in av and any(v.endswith('.rs')for v in av):
   root_job=any('/crates/ruff_text_size/' in v or v.startswith('crates/ruff_text_size/')for v in av if v.endswith('.rs'));lint=[v for v in av if 'clippy::large_stack_arrays' in v];root_src=[v for v in av if v.endswith('.rs')];c=av[av.index('--crate-name')+1]
   if root_job:assert lint==(['--allow=clippy::large_stack_arrays']if state=='older'else[]),(c,state,lint,root_src)
   comps.append(dict(crate=c,package_root=root_job,lint=lint,sources=root_src,argv_sha=digest(json.dumps(av,separators=(',',':')).encode())))
  if n in ('wild','ld','ld.bfd','rust-lld','ld.lld')and '-o'in av:links.append(dict(tool=n,argv_sha=digest(json.dumps(av,separators=(',',':')).encode())))
  if n.startswith('build-script-'):script.append(n)
 assert len(execs)>=2 and Path(execs[0][1]).samefile(proxy)and Path(execs[1][1]).samefile(V/'sdk/bin/cargo')
 def run_oracle(tag,args):
  rr=sp.run(list(map(str,args)),env=env,cwd=SRC,capture_output=True,timeout=40);(d/(tag+'.stdout')).write_bytes(rr.stdout);(d/(tag+'.stderr')).write_bytes(rr.stderr)
  return rr
 if sel=='check':
  dest=V/'lint-witness';dest.mkdir(exist_ok=True);bad=dest/'bad.rs';bad.write_text('fn main(){ruff_text_size::TextSize::intentional_missing_lint_witness();}\n')
  valid=run_oracle('valid',[rust,'+ohm','--edition=2024','--emit=metadata','--extern','ruff_text_size='+str(V/targets['library.rmeta']),V/'consumer.rs','-o',dest/'valid.rmeta']);invalid=run_oracle('invalid',[rust,'+ohm','--edition=2024','--emit=metadata','--extern','ruff_text_size='+str(V/targets['library.rmeta']),bad,'-o',dest/'bad.rmeta']);assert valid.returncode==0 and invalid.returncode!=0 and b'E0599' in invalid.stderr;oracle={'valid_exit':0,'invalid_exit':invalid.returncode,'code':'E0599','invalid_stderr':digest(invalid.stderr),'valid_rmeta':digest(dest/'valid.rmeta')}
 elif sel=='build':
  path=V/'lint-caller';rr=run_oracle('caller-build',[rust,'+ohm','--edition=2024','--extern','ruff_text_size='+str(V/targets['library.rlib']),V/'consumer.rs','-o',path]);assert rr.returncode==0,rr.stderr[-500:];rr=run_oracle('caller',[path]);assert rr.returncode==0 and rr.stdout==b'17 29 12\n'and not rr.stderr;oracle={'caller':digest(path),'value':rr.stdout.decode().strip(),'exit':0}
 else:
  path=V/targets['test'];li=run_oracle('list',[path,'--list']);run=run_oracle('tests',[path,'--test-threads=1']);assert li.returncode==run.returncode==0 and not li.stderr and not run.stderr
  tests=[l[:-6]for l in li.stdout.decode().splitlines()if l.endswith(': test')];assert sorted(tests)==['invalid_range_deserialization','range_serialization','size_serialization']and b'3 passed; 0 failed' in run.stdout;oracle={'test_sha':digest(path),'list':tests,'list_sha':digest(li.stdout),'all_passed':3}
 return dict(status=0,typed=rows,fresh=fresh,artifacts=refs,targets=targets,products=products,semantic=semantic,oracle=oracle,compile=comps,links=links,build_scripts=script,execs=execs,kernel=streams,stdout=digest(d/'stdout'),stderr=digest(d/'stderr'))
def phase(arm,sel,state,stage):
 st=PH/sel/state/arm;out=REP/sel/state/arm;assert os.geteuid()==1000 and Path('/').stat().st_uid==0 and set(os.sched_getaffinity(0))=={0,1,2,3} and int(Path('/proc/self/status').read_text().split('CapEff:\t')[1].splitlines()[0],16)==0
 role='B' if arm.startswith('B')else'A';img=ROOT/'images'/role;slot=V/'sdk/bin/cargo';assert digest(img)==S[role] and digest(V/'sdk/bin/rustc')==L['rustc']and digest(V/'sdk/lib/rustlib/x86_64-unknown-linux-gnu/bin/wild-ld/ld.bfd')==L['wild']
 assert all(digest(SRC/k)==v for k,v in srcfiles.items() if k!='Cargo.toml')
 if slot.is_symlink()or digest(slot)!=S[role]:
  d=slot.with_name('lint-study-cargo');sn=slot.stat();shutil.copyfile(img,d);d.chmod(0o500);os.utime(d,ns=(sn.st_atime_ns,sn.st_mtime_ns));os.replace(d,slot)
 assert digest(slot)==S[role] and digest(LOCK)==S['lock']
 cmd=[str(proxy),'+ohm',*selections[sel],'--locked','--offline']
 putstate(state);print('READY',flush=True)
 for packet in sys.stdin:
  name,now,action=packet.split()
  if action=='close':print('CLOSED',flush=True);return
  free=disk();d=out/name;d.mkdir();before=amark()
  if name=='cold':assert not any((V/'products').iterdir())and not any((V/'shared').iterdir())and before is None
  putstate(now)
  if action=='pair':
   import wall
   row=wall.checked_pair(sys.modules[__name__],arm,sel,state,now,d,cmd,before)
  else:
   assert action in ('native','logger')
   if action=='logger':env['CARGO_LOG']='cargo::ops::resolve=debug'
   try:row=native(d,sel,now,cmd)
   finally:
    if action=='logger':env.pop('CARGO_LOG')
   if action=='logger':
    stderr=(d/'stderr').read_bytes();row['workspace_cache_reuses']=stderr.count(b'reusing the cached workspace resolution')
  row.update(free=free,source_state=now,source_digest=digest(MAN),marker_before=before,marker_after=amark(),actual_cargo=digest(slot),lock=digest(LOCK))
  store(d/'result.json',row);print('ROW '+name,flush=True)
def leaf(sel,state,a):
    return PH/sel/state/a,REP/sel/state/a
def start(sel,state,a,kind):
    slot,out=leaf(sel,state,a);slot.mkdir(parents=True);out.mkdir(parents=True)
    for k in ('upper','work'): (slot/k).mkdir()
    base=leaf(sel,state,'A-cold')[0];trained=leaf(sel,state,a.split('-')[0]+'-trained')[0]
    root_lowers=[Path(L['old_common']),Path(L['old_lower'])]
    if kind=='trained':root_lowers.insert(0,base/'upper')
    if kind=='trial':root_lowers=[trained/'upper',base/'upper',*root_lowers]
    if kind=='cold':
        for k in ('products','shared'):(slot/k).mkdir()
    elif kind=='trained':
        assert (REP/sel/state/'A-cold'/'repeat/result.json').is_file()
        sp.run(['cp','-a','--reflink=auto',str(base/'products'),str(base/'shared'),str(slot)],check=True);assert inventory(slot)==inventory(base)
    else:
        assert kind=='trial'and (REP/sel/state/(a.split('-')[0]+'-trained')/'repeat/result.json').is_file()
        for k in ('products','shared'):
            (slot/(k+'-upper')).mkdir();(slot/(k+'-work')).mkdir()
    shell='''set -eu
slot=$1; view=$2; kind=$3; train=$4; worker=$5; arm=$6; selection=$7; historical=$8; userhome=$9; shift 9
username=$1; userlogin=$2; shift 2
chain=
for lower in "$@"; do
 mount --bind "$lower" "$lower"; mount -o remount,bind,ro "$lower"
 if test -n "$chain"; then chain=$chain:$lower; else chain=$lower; fi
done
mount -t overlay overlay -o "lowerdir=$chain,upperdir=$slot/upper,workdir=$slot/work" "$view"
mount -o remount,rw,exec,nosuid,nodev "$view"
for k in products shared; do
 if test "$kind" = trial; then
  mount --bind "$train/$k" "$train/$k"; mount -o remount,bind,ro "$train/$k"
  mount -t overlay overlay -o "lowerdir=$train/$k,upperdir=$slot/$k-upper,workdir=$slot/$k-work" "$view/$k"
  mount -o remount,rw,exec,nosuid,nodev "$view/$k"
 else
  mount --bind "$slot/$k" "$view/$k"; mount -o remount,bind,rw,exec,nosuid,nodev "$view/$k"
 fi
done
exec setpriv --reuid=1000 --regid=1000 --init-groups --no-new-privs --inh-caps=-all --ambient-caps=-all --bounding-set=-all -- env HOME="$userhome" USER="$username" LOGNAME="$userlogin" taskset -c 0-3 /usr/bin/python3 -IB "$worker" guest "$arm" "$selection" "$historical" "$kind"
'''
    args=['sudo','-n','unshare','--mount','--propagation','private','--','/bin/sh','-ec',shell,'private',str(slot),str(V),kind,str(trained),str(Path(__file__).resolve()),a,sel,state,*[env[k]for k in ('HOME','USER','LOGNAME')],*map(str,root_lowers)]
    err=(out/'guest.stderr').open('xb');proc=sp.Popen(args,cwd=ROOT,stdin=sp.PIPE,stdout=sp.PIPE,stderr=err,text=True,start_new_session=True);err.close();assert proc.stdout.readline().strip()=='READY',(name if False else a,sel,state,proc.poll())
    return proc
def send(proc,name,state,action):
    proc.stdin.write(f'{name} {state} {action}\n');proc.stdin.flush();msg=proc.stdout.readline().strip();assert msg==('CLOSED'if action=='close'else'ROW '+name),(name,state,action,msg,proc.poll())
def close(proc,state):
    send(proc,'closed',state,'close');assert proc.wait(timeout=10)==0
def clean(proc):
    if proc.poll()is None:
        try:proc.stdin.close()
        except BrokenPipeError:pass
        try:proc.wait(timeout=5)
        except sp.TimeoutExpired:os.killpg(proc.pid,signal.SIGTERM);proc.wait(timeout=10)
def warmup(sel,state):
    for arm in ('A','B'):
        name=arm+'-cold';p=start(sel,state,name,'cold')
        try:
            send(p,'cold',state,'native');send(p,'repeat',state,'native');close(p,state)
        finally:clean(p)
        r=get(REP/sel/state/name/'cold/result.json');assert any(v['package_root']for v in r['compile']);assert get(REP/sel/state/name/'repeat/result.json')['compile']==[]
        print('independent empty',sel,state,arm,len(r['compile']),len(r['links']),flush=True)
    for arm in ('A','B'):
        name=arm+'-trained';p=start(sel,state,name,'trained')
        try:
            send(p,'hydrate',state,'native');send(p,'repeat',state,'native');close(p,state)
        finally:clean(p)
        rr=get(REP/sel/state/name/'repeat/result.json');assert not rr['compile'] and not rr['links'] and all(rr['fresh'])
        store(REP/sel/state/name/'snapshot.json',inventory(leaf(sel,state,name)[0]))
def explore(sel,state):
    for arm in 'AB':
        name=arm+'-probe';p=start(sel,state,name,'trial')
        try:
            for k,s in [('base',state),('first',other(state)),('repeat',other(state)),('undo',state),('undo-repeat',state)]:send(p,k,s,'native')
            close(p,state)
        finally:clean(p)
        r=get(REP/sel/state/name/'first/result.json');u=get(REP/sel/state/name/'undo/result.json')
        print('native first/returned',sel,state,arm,len(r['compile']),len(r['links']),len(u['compile']),len(u['links']),flush=True)
def discover():
    assert socket.gethostname()==L['host']and os.geteuid()==1000;disk();PH.mkdir(mode=0o700);REP.mkdir(mode=0o700)
    for selection in selections:
        for state in ('original','older'):warmup(selection,state)
        for state in ('original','older'):explore(selection,state)
        store(REP/selection/'discovery.json',dict(selection=selection,ready=True,disk=disk()))
if __name__=='__main__':
    if sys.argv[1]=='guest':phase(*sys.argv[2:])
    elif sys.argv[1]=='discover':discover()
