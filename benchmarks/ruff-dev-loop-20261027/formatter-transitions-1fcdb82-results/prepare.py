"""Create private complete historical source views; keep the actual pinned checkout read-only."""
from pathlib import Path
import base64,hashlib,sys,subprocess,shutil,json,os
h=Path.home();w=h/'code/oss/ruff-ohm-whole-native-20261027';p=Path('/mnt/devbox-scratch/dev-user/ohm-whole-skips-20261027')
q=p/'formatter-transition-1fcdb82-v1';runtime=Path('/run/user/1000/ohm-formatter-transition-1fcdb82-v1');ram=Path('/dev/shm/ohm-formatter-transition-1fcdb82-v1')
b=json.loads(sys.stdin.buffer.read());plan=b['plan'];patch=base64.b64decode(b['patch']);f=Path(plan['rust_source'])
H=lambda b:hashlib.sha256(b).hexdigest()
assert H(patch)==plan['patch_sha256'] and subprocess.check_output(['git','rev-parse','HEAD'],cwd=w,text=True).strip()==plan['source'] and not subprocess.check_output(['git','status','--porcelain','-z'],cwd=w)
for root in (q,runtime,ram):root.mkdir(mode=0o700)
for name in ('target','shared','registry-home','receipts','src','readers','original','reversed'):(q/name).mkdir(mode=0o700)
(q/'plan.json').write_text(json.dumps(plan,indent=2,sort_keys=True)+'\n');(q/'source.patch').write_bytes(patch)
for view in ('original','reversed'):
 dest=q/view/f;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(w/f,dest)
subprocess.run(['git','apply','-R','--check',str(q/'source.patch')],cwd=q/'reversed',check=True)
subprocess.run(['git','apply','-R',str(q/'source.patch')],cwd=q/'reversed',check=True)
orig=(q/'original'/f).read_bytes();edit=(q/'reversed'/f).read_bytes();assert orig!=edit and b'pub const LINE_TERMINATORS'not in orig and b'pub const LINE_TERMINATORS'in edit
reader=q/'readers';(reader/'constant.rs').write_text('fn main() { let chars = ruff_formatter::format_element::LINE_TERMINATORS; println!("{:?}", chars); }\n')
(reader/'newlines.rs').write_text(r'''fn main() {
    for input in ["a\rb","a\r\nb","a\u{2028}b","a\u{2029}b"] {
        let value = ruff_formatter::normalize_newlines(input, ['\r','\u{2028}','\u{2029}']);
        println!("{}",value.escape_default());
    }
}
''')
sdk=p/'build-script-producer-reuse16-v1/sdk';drv,=sdk.glob('lib/librustc_driver-*.so')
def sha(f):
 with f.open('rb')as s:return hashlib.file_digest(s,'sha256').hexdigest()
images={k:sha(x)for k,x in {'cargo':sdk/'bin/cargo','frontend':sdk/'bin/rustc','driver':drv,'wild':sdk/'lib/rustlib/x86_64-unknown-linux-gnu/bin/wild-ld/ld.bfd'}.items()};assert all(plan['release'][k]==v for k,v in images.items())
v={'root':str(w),'sha_original':H(orig),'sha_reversed':H(edit),'source_relative':str(f),'sdk':str(sdk),'images':images,'reader_inputs':{r.name:sha(r)for r in reader.glob('*.rs')},'space':{str(k):shutil.disk_usage(k).free for k in [p,h,runtime,ram]}}
(q/'binding.json').write_text(json.dumps(v,indent=2,sort_keys=True)+'\n');print(json.dumps(v))
