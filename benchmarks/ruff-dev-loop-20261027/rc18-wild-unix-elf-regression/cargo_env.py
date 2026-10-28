from pathlib import Path
import os,subprocess,json,hashlib,re,shutil,sys
from importlib.util import spec_from_file_location,module_from_spec
p=Path(sys.argv[1]).resolve();p.mkdir()
def sha(b):return hashlib.sha256(b).hexdigest()
def output(p):return subprocess.run(p,capture_output=True,check=True).stdout
def arlib(name,val):
    name.mkdir();obj=name/'choice.o';r=subprocess.run(['/usr/bin/as','--64','-o',obj],input=f'.text\n.globl foreign_value\n.type foreign_value,@function\nforeign_value: mov ${val},%eax;ret\n.section .note.GNU-stack,"",@progbits\n'.encode(),capture_output=True);assert r.returncode==0;r=subprocess.run(['ar','crsD',name/'libohm_raw_name.a',obj],capture_output=True);assert not r.returncode
ascii=p/'native-ascii';wildraw=p/os.fsdecode(b'native-\xff');decoy=p/'native-�';arlib(ascii,41);arlib(wildraw,41);arlib(decoy,99)
tmpascii=p/'tmp';tmpraw=p/os.fsdecode(b'tmp-\xff');tmpascii.mkdir();tmpraw.mkdir()
proj=p/'crate';(proj/'src').mkdir(parents=True);(proj/'Cargo.toml').write_text('[package]\nname="raw_native_env"\nversion="0.0.0"\nedition="2021"\n');(proj/'src/main.rs').write_text('#[link(name="ohm_raw_name", kind="static")] unsafe extern "C" { fn foreign_value()->i32; } fn main(){println!("{}",unsafe {foreign_value()});}\n')
# Each is a separately empty target and SDK binding. No Cargo/rustc wrappers.
reports={}
for arg in sys.argv[2:]:
    tag,sdk=arg.split('=',1);sdk=Path(sdk);d=p/tag;d.mkdir();rup=d/'rustup';(rup/'toolchains').mkdir(parents=True);(rup/'toolchains/ohm').symlink_to(sdk)
    for name in ('home','cargo','shared'):(d/name).mkdir()
    rows=[]
    for case,temp,lib in [('ascii',tmpascii,ascii),('decoy',tmpascii,decoy),('raw-TMPDIR',tmpraw,ascii),('raw-LIBRARY_PATH',tmpascii,wildraw)]:
        work=d/case;work.mkdir();target=work/'target'
        env=dict(PATH=str(Path.home()/'.cargo/bin')+':/usr/local/bin:/usr/bin:/bin',HOME=str(d/'home'),USER='dev-user',RUSTUP_HOME=str(rup),RUSTUP_TOOLCHAIN='ohm',RUSTUP_AUTO_INSTALL='0',CARGO_NET_OFFLINE='true',CARGO_HOME=str(d/'cargo'),CARGO_TARGET_DIR=str(target),CARGO_BUILD_BUILD_DIR=str(d/'shared'),TMPDIR=str(temp),LIBRARY_PATH=str(lib),LANG='C.UTF-8',LC_ALL='C.UTF-8',CARGO_TERM_COLOR='never')
        tr=work/'exec.log';q=subprocess.run(['strace','-q','-f','-s','131072','-e','trace=execve','-o',tr,'cargo','+ohm','build','--offline','-j2'],cwd=proj,env=env,capture_output=True);(work/'stdout').write_bytes(q.stdout);(work/'stderr').write_bytes(q.stderr)
        raw=tr.read_bytes();exits=[l for l in raw.splitlines() if b'execve(' in l and b'"ld.bfd"' in l and l.endswith(b'= 0')];exits=[l for l in raw.splitlines() if b'/wild-ld/ld.bfd",' in l and l.endswith(b'= 0')]
        native=target/'debug/raw_native_env';rv=subprocess.run([native],capture_output=True).stdout.decode().strip()if q.returncode==0 else None
        row=dict(case=case,rc=q.returncode,value=rv,panic=b'panicked at' in q.stderr,diagnostic=q.stderr[-3500:].decode('utf8','backslashreplace').replace(str(p),'<work>'),wild_count=len(exits),wild=[dict(contains_raw=bool(re.search(rb'(?<!\\)\\377',l)),raw_arguments=[x.decode('ascii','backslashreplace').replace(str(p),'<work>')for x in re.findall(rb'"([^"]*\\377[^"]*)"',l)][:8],line_sha256=sha(l)) for l in exits],trace_sha256=sha(raw))
        rows.append(row);(d/'controls.json').write_text(json.dumps(rows,indent=2)+'\n');print(tag,case,q.returncode,rv,row['panic'],row['wild_count'],[a['contains_raw'] for a in row['wild']],flush=True)
    reports[tag]=rows
(p/'complete.json').write_text(json.dumps(reports,sort_keys=True,indent=2)+'\n')
