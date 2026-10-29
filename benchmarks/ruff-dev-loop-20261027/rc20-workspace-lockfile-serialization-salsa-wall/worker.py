"""Run a real Cargo wall cohort from an independent warm seed on a bound Linux host."""
from pathlib import Path
import ast, collections, hashlib, json, os, re, shutil, signal, socket, stat, statistics, subprocess, sys, time

ROOT=Path(__file__).resolve().parent
def get(path):return json.loads(path.read_bytes())
def digest(value):
    if isinstance(value,bytes):return hashlib.sha256(value).hexdigest()
    with Path(value).open('rb') as fd:return hashlib.file_digest(fd,'sha256').hexdigest()
def store(path,value):
    with path.open('x') as file:json.dump(value,file,sort_keys=True,indent=1);file.write('\n')
B=get(ROOT/'binding.json');P=get(ROOT/'protocol.json');T=P['toolchain']
view=Path(B['view']);disk=Path(B['physical']);reports=ROOT/'runs';cli=Path.home()/'.cargo/bin/cargo'
command=P['argv'][2:];real_argv=[str(cli),'+ohm',*command]
want_protocol='85b654185b85e9b71e49c7369c0cd4aa9bd9f4ad1cd8cb4e518501a84745e1cf'
assert digest(ROOT/'protocol.json')==want_protocol and digest(ROOT/'source-files.json')==B['source_file_digest']
def capacity():
    sizes=[shutil.disk_usage(x).free for x in [Path.home(),ROOT,disk.parent]]
    assert min(sizes[:2])>24*2**30 and sizes[2]>16*2**30,sizes
    return sizes
def poll_free(plan):
    assert socket.gethostname()==B['host'] and os.geteuid()==1000 and Path('/').stat().st_uid==0
    return capacity()
def sound_timing(argv,stdout,stderr,cwd,env):
    # Files and the argument vector have already been prepared.
    start=time.clock_gettime_ns(time.CLOCK_MONOTONIC_RAW)
    proc=subprocess.Popen(argv,cwd=cwd,env=env,stdin=subprocess.DEVNULL,stdout=stdout,stderr=stderr)
    while True:
        try:
            child,status=os.waitpid(proc.pid,0)
            break
        except InterruptedError:continue
    end=time.clock_gettime_ns(time.CLOCK_MONOTONIC_RAW)
    assert child==proc.pid and end>start
    proc.returncode=os.waitstatus_to_exitcode(status)
    return dict(pid=child,status=proc.returncode,started_ns=start,ended_ns=end,ns=end-start)
def timer():
    assert os.geteuid()==1000
    calibration=ROOT/'timer';calibration.mkdir()
    rows=[]
    with (calibration/'stdout').open('xb') as so,(calibration/'stderr').open('xb') as se:
        for i in range(7):
            for delay in ([0,15,5,25]if i%2==0 else[25,5,15,0]):
                argv=['/bin/true']if delay==0 else ['/bin/sleep',f'{delay/1000:.3f}']
                r=sound_timing(argv,so,se,calibration,dict(PATH='/usr/bin:/bin',LC_ALL='C'));assert r['status']==0
                rows.append(dict(delay_ms=delay,**r))
    res_ns=round(time.clock_getres(time.CLOCK_MONOTONIC_RAW)*1e9)
    assert 0<res_ns<=1000
    med={d:statistics.median([r['ns']/1e6 for r in rows if r['delay_ms']==d])for d in (0,5,15,25)}
    assert med[0]<10 and all(d-.2<=med[d]<=d+15 for d in (5,15,25)) and min(med[15]-med[5],med[25]-med[15])>4,med
    store(calibration/'observation.json',dict(rows=rows,medians_ms=med,clock='CLOCK_MONOTONIC_RAW',resolution_ns=res_ns,uid=os.geteuid()))
def inventory(root):
    rows={};seen={}
    for category in ('products','shared'):
        base=root/category
        for f in [base,*sorted(base.rglob('*'))]:
            name=str(f.relative_to(root));s=f.lstat();entry=[stat.S_IFMT(s.st_mode),s.st_mode&0o7777,s.st_mtime_ns,s.st_uid,s.st_gid]
            if stat.S_ISREG(s.st_mode):
                identity=(s.st_dev,s.st_ino);entry.extend([s.st_size,digest(f),seen.setdefault(identity,name)])
            elif stat.S_ISLNK(s.st_mode):entry.append(os.readlink(f))
            else:assert stat.S_ISDIR(s.st_mode)
            rows[name]=entry
    return rows
def scan_exec(dir):
    result=[];files={}
    for f in sorted(dir.glob('kernel.*')):
        files[f.name]=digest(f);pid=int(f.suffix[1:]);partial=None
        for line in f.read_text().splitlines():
            if line.startswith('execve(')and line.endswith('<unfinished ...>'):
                assert partial is None;partial=line.removesuffix('<unfinished ...>');continue
            if line.startswith('<... execve resumed>'):
                assert partial is not None;line=partial+line[len('<... execve resumed>'):];partial=None
            if not line.startswith('execve(')or not line.endswith('= 0'):continue
            m=re.match(r'execve\(("(?:[^"\\]|\\.)*"), (\[.*\]), (?:0x|NULL|\[)',line);assert m,line[:180]
            result.append([pid,ast.literal_eval(m[1]),ast.literal_eval(m[2])])
        assert partial is None
    return files,result
def enter(arm):
    st=disk/arm;out=reports/arm;src=view/'source';mf=src/'Cargo.toml';lockfile=src/'Cargo.lock';storefiles=get(ROOT/'source-files.json')
    assert os.geteuid()==1000 and Path('/').stat().st_uid==0 and set(os.sched_getaffinity(0))==set(B['program_cpu'])
    assert int(Path('/proc/self/status').read_text().split('CapEff:\t')[1].splitlines()[0],16)==0
    assert all((view/k).samefile(st/k)for k in ('products','shared'))
    env=get(Path(B['prior_enrollment']))['env'];assert env['CARGO_TARGET_DIR']==str(view/'products') and env['CARGO_BUILD_BUILD_DIR']==str(view/'shared') and env['RUSTUP_HOME']==str(view/'ru')
    assert not set(env)&{'LD_PRELOAD','RUSTC_WRAPPER','RUSTC_WORKSPACE_WRAPPER','RUSTFLAGS','CARGO_LOG','CARGO_ENCODED_RUSTFLAGS'}
    assert env['CARGO_NET_OFFLINE']=='true'
    sdk=view/'sdk';actual=sdk/'bin/cargo';img=Path(B['images']['A'if arm=='C'else arm]);sha=T['baseline'if arm!='B'else'candidate'];assert digest(img)==sha and all(digest(src/k)==v for k,v in storefiles.items())
    assert digest(sdk/'bin/rustc')==T['rustc'] and digest(sdk/'lib/rustlib/x86_64-unknown-linux-gnu/bin/wild-ld/ld.bfd')==T['wild']
    if actual.is_symlink()or digest(actual)!=sha:
        st0=actual.stat();private=actual.with_name('salsa-wall-cargo-install');shutil.copyfile(img,private);private.chmod(0o500);os.utime(private,ns=(st0.st_atime_ns,st0.st_mtime_ns));os.replace(private,actual)
    assert not actual.is_symlink() and digest(actual)==sha
    old=mf.read_bytes();start=b'salsa = { version = "0.28.5", default-features = false, features = [\n';assert old.count(start)==1;new=old.replace(start,start.replace(b'0.28.5',b'0.28.2'));texts={'original':old,'reversed':new}
    assert digest(old)==P['historical']['original'] and digest(new)==P['historical']['reversed'] and digest(lockfile)==T['lockfile']
    resolver=view/'products/.cargo-resolve-cache-v1';consumer=view/'salsa-wall-consumer';member='ruff_text_size'
    def anchor(name):
        return get(reports/'C'/'common-settled'/'result.json')if name!='C'or (reports/'C'/'common-settled'/'result.json').is_file()else None
    def fresh_paths(row):return {k:digest(view/k)for k in row['files']}
    def marker():return digest(resolver)if resolver.is_file()else None
    def ordinary(cmd):return subprocess.run(cmd,cwd=src,env=env,capture_output=True,timeout=120)
    def native(name,state,d,prior):
        code=ordinary(['strace','-ff','-qq','-s','131072','-e','trace=process','-o',str(d/'kernel'),*real_argv,'--message-format=json']);(d/'stdout').write_bytes(code.stdout);(d/'stderr').write_bytes(code.stderr);assert code.returncode==0,code.stderr[-1200:]
        messages=[json.loads(l)for l in code.stdout.splitlines()];assert messages[-1]=={'reason':'build-finished','success':True}
        artifact,=[m for m in messages if m['reason']=='compiler-artifact'];assert artifact['target']['name']==member and artifact['target']['kind']==['lib'] and not artifact['features']
        files={str(Path(k).relative_to(view)):digest(k)for k in artifact['filenames']};assert len(files)==2 and {Path(k).suffix for k in files}=={'.rlib','.rmeta'}
        wire,execs=scan_exec(d);work=[]
        for _,path,args in execs:
            tool=Path(path).name
            if tool=='rustc' and '--crate-name'in args and any(v.endswith('.rs')for v in args):work.append([tool,args[args.index('--crate-name')+1]])
            elif tool in ('ld.bfd','ld','wild','lld','rust-lld','cc','collect2')and '-o'in args:work.append([tool,'link'])
            elif tool.startswith('build-script-'):work.append([tool,'build-script'])
        cold=name=='common-cold'
        assert artifact['fresh']==(not cold) and work==([['rustc',member]]if cold else[])
        assert len(execs)>2 if cold else len(execs)==2
        assert Path(execs[0][1]).samefile(cli) and Path(execs[1][1]).samefile(actual) and execs[0][2][1:]==real_argv[1:]+['--message-format=json'] and execs[1][2][1:]==command+['--message-format=json']
        lib,=[v for v in artifact['filenames']if v.endswith('.rlib')]
        build=ordinary([str(cli.parent/'rustc'),'+ohm','--edition=2024','--extern','ruff_text_size='+lib,str(view/'consumer.rs'),'-o',str(consumer)]);(d/'caller-build.stderr').write_bytes(build.stderr);assert build.returncode==0
        value=ordinary([str(consumer)]);(d/'caller.stdout').write_bytes(value.stdout);(d/'caller.stderr').write_bytes(value.stderr);assert value.returncode==0 and value.stdout==b'17 29 12\n' and not value.stderr
        roster=[artifact['package_id'],member,['lib'],[]];ret=dict(stdout=digest(code.stdout),stderr=digest(code.stderr),files=files,caller=digest(consumer),caller_value=value.stdout.decode().strip(),caller_output=digest(value.stdout),roster=roster,compiler_work=work,execs=execs,kernel=wire,success=True,fresh=artifact['fresh'])
        if prior:assert ret['files']==prior['files'] and ret['roster']==prior['roster'] and ret['caller']==prior['caller']
        return ret
    def timings(d,common,from_marker):
        assert from_marker and fresh_paths(common)==common['files'] and digest(consumer)==common['caller']
        handles=[(d/name).open('xb',buffering=0)for name in ('edit.stdout','edit.stderr','repeat.stdout','repeat.stderr')]
        try:
            edit=sound_timing(real_argv,handles[0],handles[1],src,env)
            mid=marker()
            repeated=sound_timing(real_argv,handles[2],handles[3],src,env)
        finally:
            for fd in handles:fd.close()
        assert edit['status']==repeated['status']==0 and edit['ended_ns']<=repeated['started_ns']
        assert from_marker!=mid and mid==marker()
        streams={k:digest(d/k)for k in ('edit.stdout','edit.stderr','repeat.stdout','repeat.stderr')}
        for stage in ('edit','repeat'):
            assert (d/(stage+'.stdout')).stat().st_size==0;err=(d/(stage+'.stderr')).read_bytes();assert b'Finished' in err and all(x not in err for x in (b'Compiling',b'Checking',b'Running ',b'error:')),err
        assert fresh_paths(common)==common['files'] and digest(consumer)==common['caller']
        return dict(edit=edit,repeat=repeated,streams=streams,mid_marker=mid,files=common['files'],caller=common['caller'],argv=real_argv)
    print('READY',flush=True)
    for request in sys.stdin:
        name,state,action=request.split()
        if action=='close':
            assert mf.read_bytes()==old and digest(lockfile)==T['lockfile'] and digest(actual)==sha
            print('CLOSED',flush=True);return
        free=capacity();d=out/name;d.mkdir()
        src_text=texts[state];before=marker()
        if mf.read_bytes()!=src_text:mf.write_bytes(src_text)
        assert mf.read_bytes()==src_text and digest(lockfile)==T['lockfile']
        common=anchor(arm)
        if name=='common-cold':assert arm=='C' and before is None and all(not any((view/k).iterdir()) for k in ('products','shared'))
        if action=='native':r=native(name,state,d,common)
        else:
            assert action=='pair' and common
            r=timings(d,common,before)
            established=get(out/('pre-reverse' if state=='reversed'else'pre-restore')/'result.json')
            assert (before,r['mid_marker'])==(established['marker_before'],established['marker_after'])
        after=marker();assert after and digest(mf)==digest(src_text) and digest(lockfile)==T['lockfile']
        r.update(name=name,state=state,mode=action,arm=arm,source_sha=digest(src_text),marker_before=before,marker_after=after,room=free,image=sha,lock=T['lockfile'])
        store(d/'result.json',r);print('ROW '+name,flush=True)
def start(a,stage):
    state=disk/a
    layers=[Path(B['old_common']),Path(B['lower'])] if a=='C'else[disk/'C/upper',Path(B['old_common']),Path(B['lower'])]
    shell='''
set -eu
state=$1; view=$2; worker=$3; arm=$4; affinity=$5; guest_home=$6; guest_user=$7; guest_login=$8; shift 8
chain=
for lower in "$@"; do
    mount --bind "$lower" "$lower"
    mount -o remount,bind,ro "$lower"
    if test -z "$chain"; then chain=$lower; else chain=$chain:$lower; fi
done
mount -t overlay overlay -o "lowerdir=$chain,upperdir=$state/upper,workdir=$state/work" "$view"
mount -o remount,rw,exec,nosuid,nodev "$view"
for which in products shared; do
    mount --bind "$state/$which" "$view/$which"
    mount -o remount,bind,rw,exec,nosuid,nodev "$view/$which"
done
exec setpriv --reuid=1000 --regid=1000 --init-groups --no-new-privs --inh-caps=-all --ambient-caps=-all --bounding-set=-all -- env HOME="$guest_home" USER="$guest_user" LOGNAME="$guest_login" taskset -c "$affinity" /usr/bin/python3 -IB "$worker" guest "$arm"
'''
    argv=['sudo','-n','unshare','--mount','--propagation','private','--','/bin/sh','-ec',shell,'private',str(state),str(view),str(Path(__file__).resolve()),a,','.join(map(str,B['program_cpu'])),*[get(Path(B['prior_enrollment']))['env'][k] for k in ('HOME','USER','LOGNAME')],*map(str,layers)]
    err=(reports/(stage+'-'+a+'.stderr')).open('xb')
    proc=subprocess.Popen(argv,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=err,text=True,start_new_session=True)
    err.close()
    ready=proc.stdout.readline().strip();assert ready=='READY',(a,stage,proc.poll(),ready)
    return proc
def end(proc):
    if proc.poll()is None:
        try:proc.stdin.close()
        except BrokenPipeError:pass
        try:proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            os.killpg(proc.pid,signal.SIGTERM);proc.wait(timeout=8)
def ordering():
    rr=P['schedule'];assert len(rr)==32 and [v['pair']for v in rr]==list(range(1,33))
    assert collections.Counter((r['direction'],r['order'])for r in rr)=={(d,o):8 for d in ('reverse','restore')for o in ('AB','BA')}
    return rr
def master(action):
    poll_free(P);expected=ordering();os.sched_setaffinity(0,set(B['supervisor_cpu']))
    trace=[]
    def send(proc,a,k,state,kind):
        proc.stdin.write(f'{k} {state} {kind}\n');proc.stdin.flush()
        msg=proc.stdout.readline().strip();assert msg==('CLOSED'if kind=='close'else'ROW '+k),(a,k,msg,proc.poll())
        trace.append([a,k,state,kind])
    def new(a,create):
        state=disk/a;state.mkdir()
        for k in ('upper','work'): (state/k).mkdir()
        if create:
            for k in ('products','shared'):(state/k).mkdir()
        (reports/a).mkdir()
    def flank(arms,section):
        phases=[('base','original'),('reverse','reversed'),('reverse-repeat','reversed'),('restore','original'),('restore-repeat','original')]
        for a in arms:
            for phase,state in phases:
                name=section+'-'+phase;send(arms[a],a,name,state,'native')
                r=get(reports/a/name/'result.json')
                assert (r['marker_before']!=r['marker_after'])==(phase in ('reverse','restore')),(a,name,r['marker_before'],r['marker_after'])
    if action=='admit':
        assert not reports.exists() and not disk.exists() and not (ROOT/'timer').exists()
        disk.mkdir(mode=0o700);reports.mkdir(mode=0o700);new('C',True)
        path=ROOT/'timer.kernel'
        subprocess.run(['taskset','-c',','.join(map(str,B['timer_cal_cpu'])),'strace','-qq','-s','1024','-e','trace=wait4,waitid','-o',str(path),'/usr/bin/python3','-IB',str(Path(__file__).resolve()),'timer'],check=True,timeout=60)
        obs=get(ROOT/'timer/observation.json');waits=[]
        for l in path.read_text().splitlines():
            if not l.startswith('wait4('):continue
            m=re.match(r'wait4\((\d+), .*?, 0, NULL\)\s+=\s+(\d+)$',l);assert m and m[1]==m[2],l
            waits.append(int(m[1]))
        assert waits==[r['pid']for r in obs['rows']] and len(waits)==28
        store(ROOT/'timer/verified.json',dict(complete=True,num=28,raw=digest(path),evidence=digest(ROOT/'timer/observation.json'),actual_blocking_kernel_pids=waits))
        c=start('C','seed')
        try:
            for k in ('common-cold','common-settled'):send(c,'C',k,'original','native')
            send(c,'C','close','original','close');assert c.wait(timeout=30)==0
        finally:end(c)
        cold=get(reports/'C/common-cold/result.json');settled=get(reports/'C/common-settled/result.json');assert cold['files']==settled['files'] and cold['caller']==settled['caller'] and cold['marker_before']is None and settled['marker_before']==settled['marker_after']==cold['marker_after']
        common=inventory(disk/'C');store(ROOT/'seed-inventory.json',common);assert len(common)>15
        for a in 'AB':
            new(a,False)
            subprocess.run(['cp','-a','--reflink=auto',str(disk/'C/products'),str(disk/'C/shared'),str(disk/a)],check=True)
            assert inventory(disk/a)==common,(a,'reopen cloned targets')
        store(ROOT/'seed.json',dict(files=settled['files'],caller=settled['caller'],cold=digest(reports/'C/common-cold/result.json'),settled=digest(reports/'C/common-settled/result.json'),physical_inventory=digest(ROOT/'seed-inventory.json'),count=len(common),fresh=True,original_h8_instruction_matches=sorted(settled['files'].values())==sorted(['9afcd7b81653b5d7c7cfa11d5612737f763e71fb80cb0ae923e4b893910c46d1','af8f228d9e5e76c736b54649f65b2d4089f01edc16ee615df49142e8f373f9a9']),independent_state_inodes={a:{k:[(disk/a/k).stat().st_dev,(disk/a/k).stat().st_ino]for k in ('products','shared')}for a in 'CAB'}))
    else:
        assert action=='score' and (ROOT/'admitted.json').exists() and not (ROOT/'score-started.json').exists()
        store(ROOT/'score-started.json',dict(plan=want_protocol,admission=digest(ROOT/'admitted.json'),worker=digest(Path(__file__)),physical_free=capacity(),system_load=os.getloadavg()))
    arms={}
    try:
        for a in 'AB':arms[a]=start(a,action)
        if action=='admit':flank(arms,'pre')
        else:
            for slot in expected:
                for a in slot['order']:
                    name='s'+str(slot['pair']).zfill(2)
                    send(arms[a],a,name,slot['state'],'pair')
                    # The arms validated their own source marker and verdict. The supervisor only sees completion.
                    if not (reports/a/name/'result.json').is_file():raise RuntimeError(name)
                print('qualified pair',slot['pair'],flush=True)
            flank(arms,'post')
        for a in 'BA':
            send(arms[a],a,'close','original','close');assert arms[a].wait(timeout=30)==0
    finally:
        for proc in arms.values():end(proc)
    store(ROOT/('admitted.json'if action=='admit'else'terminal.json'),dict(ok=True,plan=want_protocol,worker=digest(Path(__file__)),seed=digest(ROOT/'seed.json'),timer=digest(ROOT/'timer/verified.json'),phase=action,operations=trace,physical_free=capacity(),load=os.getloadavg(),record_count=sum(k[3]=='pair'for k in trace)))
if __name__=='__main__':
    if sys.argv[1]=='guest': enter(sys.argv[2])
    elif sys.argv[1]=='timer':timer()
    else:master(sys.argv[1])
