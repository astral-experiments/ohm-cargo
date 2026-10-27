"""Count actual Rust target closure risks using the official release and unmodified Ruff manifests."""
from collections import deque
from pathlib import Path
import fcntl,hashlib,json,os,shutil,socket,subprocess,sys
p=Path('/mnt/devbox-scratch/dev-user/ohm-whole-skips-20261027');x=Path.home()/'.cache/ohm-233-position-qualified-20261027';d=p/'build-script-producer-reuse16-v1';w=Path.home()/'code/oss/ruff-ohm-whole-native-20261027';g=d/'unit-graphs';g.mkdir(exist_ok=True)
orig='93526150df078af7dd8fc4226cdcc469539d2001'
assert subprocess.check_output(['git','rev-parse','HEAD'],cwd=w,text=True).strip()==orig
assert not subprocess.check_output(['git','status','--porcelain','-uno'],cwd=w)
reg=d/'graph-registry';source=x/'mixed-alloc-same-compiler-qualification-v1/state/build/C/registry-home'
with (p/'native-measure.lock').open('rb') as lock:
    fcntl.flock(lock,fcntl.LOCK_EX)
    if not reg.exists():subprocess.run(['cp','-a','--reflink=auto',str(source),str(reg)],check=True)
    env=dict(HOME=str(Path.home()),PATH=str(Path.home()/'.cargo/bin')+':/usr/local/bin:/usr/bin:/bin',LC_ALL='C.UTF-8',RUSTUP_HOME=str(d/'rustup'),RUSTUP_AUTO_INSTALL='0',CARGO_HOME=str(reg),CARGO_TARGET_DIR=str(g/'target'),CARGO_BUILD_BUILD_DIR=str(g/'shared'),CARGO_BUILD_JOBS='8',GIT_OPTIONAL_LOCKS='0',CARGO_NET_OFFLINE='true')
    bymode={}
    for mode in ('check','build','test'):
        argv=['cargo','+ohm','-Zunstable-options',mode,'--unit-graph','--offline','--locked']+(['--no-run'] if mode=='test' else [])
        r=subprocess.run(argv,cwd=w,env=env,capture_output=True);(g/(mode+'.stdout')).write_bytes(r.stdout);(g/(mode+'.stderr')).write_bytes(r.stderr);assert not r.returncode,(mode,r.stderr[-300:])
        ugraph=json.loads(r.stdout);us=ugraph['units']
        def sources(i):return [q['index'] for q in us[i]['dependencies']]
        def pathname(i):return us[i]['target']['name']
        def is_local(i):return us[i]['pkg_id'].startswith('path+')
        def is_pm(i):return 'proc-macro' in us[i]['target']['kind']
        def closure(i):
            visited={i:None};work=deque([i]);pmlist=[];ws=[]
            while work:
                ix=work.popleft()
                if is_pm(ix):
                    chain=[ix]
                    while visited[chain[-1]] is not None:chain.append(visited[chain[-1]])
                    q=[pathname(cc) for cc in reversed(chain)]
                    pmlist.append(q)
                    if is_local(ix):ws.append(q)
                for y in sources(ix):
                    if y not in visited:visited[y]=ix;work.append(y)
            return sorted(ws,key=lambda q:(len(q),q)),sorted(pmlist,key=lambda q:(len(q),q))
        rows=[]
        for i,m in enumerate(us):
            if not is_local(i):continue
            s=Path(m['target']['src_path']);source_rel=str(s.relative_to(w)) if s.is_relative_to(w) else str(s.name)
            if not (source_rel.startswith(('crates/ty/','crates/ruff/','crates/ty_wasm/')) or m['target']['name']=='ruff_dev'):continue
            if m['mode'] not in ['check','build','test']:continue
            if 'custom-build' in m['target']['kind']:continue
            wm,pm=closure(i)
            rows.append(dict(id=i,mode=m['mode'],kind=m['target']['kind'],crate=pathname(i),source=source_rel,local_macro_chains=wm,registry_macros=[q[-1] for q in pm if q not in wm],shortest_registry_chain=next((q for q in pm if q not in wm),None),direct_local_macro=[pathname(k) for k in sources(i) if is_pm(k) and is_local(k)],direct_macro=[pathname(k) for k in sources(i) if is_pm(k)]))
        bymode[mode]={'argc':argv,'raw_hash':hashlib.sha256(r.stdout).hexdigest(),'num_units':len(us),'num_roots':len(ugraph['roots']),'rows':rows}
    (g/'result.json').write_text(json.dumps(bymode,sort_keys=True,indent=2)+'\n');print(json.dumps(bymode))
