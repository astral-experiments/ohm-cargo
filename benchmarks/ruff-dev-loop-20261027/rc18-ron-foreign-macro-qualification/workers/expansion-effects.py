"""Inspect syscalls with real native proc-macro frames, under a sealed ordinary Cargo invocation."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import socket
import subprocess
import threading

OPS = ('open,openat,openat2,readlink,readlinkat,access,faccessat,faccessat2,getdents64,'
       'connect,socket,getrandom,clock_gettime,time,gettimeofday,execve')
DSO = re.compile(rb'/(lib(?:serde_derive|ambient_macro)-[A-Fa-f0-9]+\.so)\(([^)]*)\)')
CALL = re.compile(rb'^([a-z0-9_]+)\(')

def sha(p):
    with p.open('rb') as f: return hashlib.file_digest(f,'sha256').hexdigest()

def inspect(root, out, kind):
    out.mkdir(); base=root/('registry' if kind=='ron' else 'ambient');ws=base/('source' if kind=='ron' else '.');state=base/'warm'
    exe='ron_native_probe' if kind=='ron' else 'observed_ambient'
    env={k:v for k,v in os.environ.items() if not k.startswith(('RUST','CARGO','OHM_'))}
    env.update(RUSTUP_AUTO_INSTALL='0',RUSTUP_HOME=str(root/'rustup'),CARGO_NET_OFFLINE='true',CARGO_TERM_COLOR='never',PATH=str(Path.home()/'.cargo/bin')+':/usr/local/bin:/usr/bin:/bin',
        CARGO_TARGET_DIR=str(state/'target'),CARGO_BUILD_BUILD_DIR=str(state/'shared'),CARGO_HOME=str(state/'cargo'))
    args=['cargo','+ohm','build','--locked','--offline','-j8','--message-format=json']
    capture=['strace','-ff','-qq','-k','-s','256','-e','trace='+OPS,'-o',str(out/'calls')]
    sock=None;received=[]
    if kind=='socket':
        args+=['-p',exe]; path=Path('/tmp')/('ohm-amb-'+hashlib.sha256(os.fsencode(root)).hexdigest()[:20]+'.sock')
        assert not path.exists();sock=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM);sock.bind(str(path));sock.listen();sock.settimeout(165)
        env['OHM_AMBIENT_SOCKET']=str(path)
        def send():
            con,_=sock.accept()
            with con: con.sendall(b'17')
            received.append(17)
        thread=threading.Thread(target=send,daemon=True);thread.start()
    try:
        with (out/'stdout').open('xb') as so,(out/'stderr').open('xb') as se:
            p=subprocess.run(capture+args,cwd=ws,env=env,stdout=so,stderr=se,timeout=160)
        if p.returncode: raise RuntimeError((p.returncode,(out/'stderr').read_text()[-1800:]))
        if sock is not None: thread.join(timeout=3);assert received==[17]
    finally:
        if sock is not None:sock.close();path.unlink(missing_ok=True)
    messages=[json.loads(s) for s in (out/'stdout').read_bytes().splitlines()];artifacts=[r for r in messages if r.get('reason')=='compiler-artifact']
    main,=[r for r in artifacts if r['target']['name']==exe];assert not main['fresh'];run=subprocess.check_output([main['executable']],text=True).strip();assert run==('2' if kind=='ron' else '2 17')
    proc={r['target']['name']:sha(Path(r['filenames'][0])) for r in artifacts if r['target']['kind']==['proc-macro']}
    if kind=='ron': assert not next(r for r in artifacts if r['target']['name']=='ron')['fresh']
    groups=[];files={};nr=0;has_stack=0;unwind_failure=0
    for f in sorted(out.glob('calls.*')):
        files[f.name]=sha(f)
        op=None;stack=[];line=b''
        def finish():
            nonlocal nr,has_stack,unwind_failure
            if op is None:return
            nr+=1; has_stack+=bool(stack)
            if any(b'unwind' in t.lower() and b'failed' in t.lower() for t in stack):unwind_failure+=1
            selected=[]
            for t in stack:
                m=DSO.search(t)
                if m:selected.append((m[1].decode(),m[2].decode(errors='backslashreplace')[:350]))
            if selected:
                groups.append({'trace':f.name,'call':op,'line_sha256':hashlib.sha256(line).hexdigest(),
                    'stack_sha256':hashlib.sha256(b'\n'.join(stack)).hexdigest(),'macro_frames':selected})
        with f.open('rb') as stream:
            for raw in stream:
                if raw.startswith(b' >'):
                    if op is not None:stack.append(raw.rstrip())
                    continue
                finish();stack=[];op=None;line=raw.rstrip()
                m=CALL.match(raw)
                if m:op=m[1].decode()
        finish()
    assert nr and has_stack
    if kind=='socket':
        assert any(r['call']=='connect' and any('libambient_macro' in m[0] for m in r['macro_frames']) for r in groups), groups
    report={'fixture':kind,'processes':len(files),'calls':nr,'calls_with_stack':has_stack,'possible_unwind_failures':unwind_failure,'macro_stack_calls':groups,
        'trace_sha256':files,'binary':sha(Path(main['executable'])),'program':run,'proc_macros':proc,'selected_syscalls':OPS.split(','),
        'scope':'Observed syscalls with a physically resolved native macro DSO frame. Non-systemcall inputs including vDSO time, opaque native callbacks and constructors are outside this attribution.'}
    (out/'report.json').write_text(json.dumps(report,indent=2,sort_keys=True)+'\n')
    from collections import Counter
    print(json.dumps({'fixture':kind,'calls':nr,'stacks':has_stack,'observations':Counter(r['call'] for r in groups)}),flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('root',type=Path);p.add_argument('out',type=Path);p.add_argument('kind',choices=('ron','socket'));args=p.parse_args();inspect(args.root,args.out,args.kind)
