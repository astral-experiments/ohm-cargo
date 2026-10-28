"""A stable Rust caller has a genuine serde foreign join and one native, undeclared input."""
import hashlib
import json
import os
from pathlib import Path
import queue
import shutil
import socket
import subprocess
import sys
import threading


def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()


def run(root):
    src=root/'ambient';src.mkdir();(src/'.cargo').mkdir();shutil.copyfile(root/'registry/source/.cargo/config.toml',src/'.cargo/config.toml')
    def save(relative,text):
        p=src/relative;p.parent.mkdir(exist_ok=True,parents=True);p.write_text(text);return p
    save('Cargo.toml','[workspace]\nresolver="2"\nmembers=["app","ambient_macro"]\n')
    save('app/Cargo.toml','[package]\nname="observed_ambient"\nversion="0.0.0"\nedition="2021"\n[dependencies]\nambient_macro={path="../ambient_macro"}\nbitflags={version="=2.13.2", features=["serde"]}\nserde="=1.0.229"\nserde_derive="=1.0.229"\n')
    save('ambient_macro/Cargo.toml','[package]\nname="ambient_macro"\nversion="0.0.0"\nedition="2021"\n[lib]\nproc-macro=true\n')
    save('ambient_macro/src/lib.rs','''extern crate proc_macro;
use std::io::Read;
#[proc_macro]
pub fn sample(_: proc_macro::TokenStream) -> proc_macro::TokenStream {
    let mut stream = std::os::unix::net::UnixStream::connect(std::env::var_os("OHM_AMBIENT_SOCKET").unwrap()).unwrap();
    let mut value = String::new();stream.read_to_string(&mut value).unwrap();
    match value.as_str() {"17"|"29" => value.parse().unwrap(), _ => panic!("unexpected value")}
}
''')
    save('app/src/main.rs','''use serde_derive::{Serialize,Deserialize};
bitflags::bitflags! {
    #[derive(Debug, Copy, Clone, PartialEq, Eq, Serialize, Deserialize)]
    pub struct Flags: usize { const FIELD = 2; }
}
fn main() { println!("{} {}",Flags::FIELD.bits(),ambient_macro::sample!()); }
''')
    shutil.copyfile(root/'registry/source/Cargo.lock',src/'Cargo.lock')
    # This server's argv, path, backing inode and metadata stay fixed across all four compiles.
    sockpath=Path('/tmp')/('ohm-amb-'+hashlib.sha256(os.fsencode(root)).hexdigest()[:20]+'.sock')
    with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as server:
        assert not sockpath.exists();server.bind(str(sockpath));server.listen();server.settimeout(40)
        try:
            orig=sockpath.stat();hist=[]
            env={k:v for k,v in os.environ.items() if not k.startswith(('RUST','CARGO','OHM_'))}
            env.update(OHM_AMBIENT_SOCKET=str(sockpath),RUSTUP_AUTO_INSTALL='0',RUSTUP_HOME=str(root/'rustup'),
                PATH=str(Path.home()/'.cargo/bin')+':/usr/local/bin:/usr/bin:/bin',CARGO_NET_OFFLINE='true',CARGO_TERM_COLOR='never')
            received=queue.Queue()
            def serve_one(value):
                try:
                    con,_=server.accept()
                    with con:con.sendall(str(value).encode())
                    received.put(value)
                except Exception as e:received.put(repr(e))
            for label,value,arm in [('first',17,'warm'),('value-change',29,'warm'),('unchanged',29,'warm'),('return',17,'warm'),('independent',17,'clean')]:
                state=src/arm;state.mkdir(exist_ok=True);out=src/label;out.mkdir();runner=threading.Thread(target=serve_one,args=(value,),daemon=True);runner.start()
                proc_env=dict(env,CARGO_TARGET_DIR=str(state/'target'),CARGO_BUILD_BUILD_DIR=str(state/'shared'),CARGO_HOME=str(state/'cargo'))
                args=['cargo','+ohm','build','--offline','-p','observed_ambient','--message-format=json','-j8'];
                if label!='first':args.append('--locked')
                with (out/'out').open('xb') as so,(out/'err').open('xb') as err:
                    p=subprocess.run(['strace','-ff','-qq','-s','32768','-e','trace=execve,connect','-o',str(out/'exec')]+args,cwd=src,env=proc_env,stdout=so,stderr=err,timeout=115)
                if p.returncode:raise RuntimeError((label,p.returncode,(out/'err').read_text()[-600:],(out/'out').read_text()[-1500:]))
                runner.join(timeout=2);assert not runner.is_alive() and received.get_nowait()==value
                msgs=[json.loads(line) for line in (out/'out').read_bytes().splitlines()];arts=[r for r in msgs if r.get('reason')=='compiler-artifact'];app,=[r for r in arts if r['target']['name']=='observed_ambient'];exe=Path(app['executable'])
                result=subprocess.check_output([exe],text=True).strip();assert result==f'2 {value}' and not app['fresh']
                dep,=[p for p in (state/'target').rglob('*.d') if p.parent.name=='out' and p.name.startswith('observed_ambient') and b'ohm-foreign-span-bytes' in p.read_bytes()]
                fp=dep.parent.parent/'fingerprint/dep-bin-observed_ambient';enc=fp.read_bytes();assert enc[-41:-37]==b'OBS1' and enc[-33]==0
                assert os.fsencode(sockpath) not in dep.read_bytes() and os.fsencode(sockpath) not in enc
                inputs={}
                for a in arts:
                    if a['target']['name'] in ('serde_derive','ambient_macro','bitflags','serde') and 'custom-build' not in a['target']['kind']:
                        inputs[a['target']['name']]=[sha(Path(n)) for n in a['filenames']]
                assert len(inputs)==4
                matches=[]
                for f in out.glob('exec.*'):
                    lines=f.read_bytes().splitlines()
                    if any(b'"--crate-name", "observed_ambient"' in ln and ln.rstrip().endswith(b'= 0') for ln in lines):matches.append(f.name)
                assert len(matches)==1
                sockets=[f.name for f in out.glob('exec.*') if any(os.fsencode(sockpath) in l and l.startswith(b'connect(') and l.endswith(b'= 0') for l in f.read_bytes().splitlines())];assert sockets
                st=sockpath.stat();assert (st.st_dev,st.st_ino,st.st_mtime_ns,st.st_ctime_ns)==(orig.st_dev,orig.st_ino,orig.st_mtime_ns,orig.st_ctime_ns)
                hist.append({'phase':label,'program':result,'app_fresh':app['fresh'],'compiler_trace':matches,'socket_traces':sockets,
                    'inputs':inputs,'compiled_app_sha':sha(exe),'dep_info':sha(dep),'cargo_encoded':sha(fp),'native_marker':True,
                    'socket_present_in_declared_inputs':False,'external_socket_inode_and_times_stable':True,'trace_sha256':{f.name:sha(f) for f in out.glob('exec.*')}})
                print(label,result,flush=True)
            assert all(r['inputs']==hist[0]['inputs'] for r in hist[:4]);assert all(r['dep_info']==hist[0]['dep_info'] for r in hist[:4])
            return hist
        finally:sockpath.unlink(missing_ok=True)


if __name__=='__main__':
    root=Path(sys.argv[1]);result=run(root);(root/'ambient.json').write_text(json.dumps(result,sort_keys=True,indent=2)+'\n')
