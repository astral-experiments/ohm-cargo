"""Compare a normal compiler-option transition against an empty build and a real recompilation."""
from pathlib import Path
import hashlib
import json
import os
import shutil
import subprocess
import sys


def digest(p):
    with p.open('rb') as src:
        return hashlib.file_digest(src, 'sha256').hexdigest()


if len(sys.argv) != 5:
    raise SystemExit('usage: qualify-relink-collection-verdict.py DEST SDK CARGO_SHA RUSTC_SHA')
dest, sdk = (Path(p).resolve() for p in sys.argv[1:3])
assert not dest.exists() and (sdk/'bin/cargo').is_file()
assert digest(sdk/'bin/cargo') == sys.argv[3] and digest(sdk/'bin/rustc') == sys.argv[4]
assert shutil.disk_usage(dest.parent).free > 45*2**30 + 600*2**20
dest.mkdir(mode=0o700)
source=dest/'source'
files={
    'Cargo.toml':'[workspace]\nresolver="3"\nmembers=["report","facade","consumer"]\n',
    'report/Cargo.toml':'[package]\nname="report"\nversion="0.1.0"\nedition="2024"\n[lib]\nproc-macro=true\n',
    'report/src/lib.rs': '''extern crate proc_macro;
#[proc_macro]
pub fn check_invocation(_: proc_macro::TokenStream) -> proc_macro::TokenStream {
    if std::env::args_os().any(|arg| arg == "emit-rlink" || arg == "-Zemit-rlink") {
        "17u8".parse().unwrap()
    } else {
        "compile_error!(\\\"link recipe was not requested\\\")".parse().unwrap()
    }
}
''',
    'facade/Cargo.toml':'[package]\nname="facade"\nversion="0.1.0"\nedition="2024"\n[dependencies]\nreport={path="../report"}\n',
    'facade/src/lib.rs':'pub use report::check_invocation;\n',
    'consumer/Cargo.toml':'[package]\nname="consumer"\nversion="0.1.0"\nedition="2024"\n[dependencies]\nfacade={path="../facade"}\n',
    'consumer/src/main.rs':'fn main() { println!("{}", facade::check_invocation!()); }\n',
}
for name, data in files.items():
    p=source/name
    p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(data)
rs=dest/'rustup'
(rs/'toolchains').mkdir(parents=True)
(rs/'toolchains/ohm').symlink_to(sdk,target_is_directory=True)
(rs/'settings.toml').write_text('version = "12"\nprofile = "minimal"\n')
for name in ('cargo-home','tmp','logs','escrow'): (dest/name).mkdir()
env={k:os.environ[k] for k in ('HOME','USER','LOGNAME') if k in os.environ}
env.update(PATH=str(Path.home()/'.cargo/bin')+':/usr/bin:/bin',RUSTUP_HOME=str(rs),CARGO_HOME=str(dest/'cargo-home'),
           CARGO_NET_OFFLINE='true',CARGO_TERM_COLOR='never',CARGO_CACHE_AUTO_CLEAN_FREQUENCY='never',
           TMPDIR=str(dest/'tmp'),LC_ALL='C.UTF-8',TZ='UTC')
pins={k:subprocess.check_output([k,'+ohm','-Vv'],cwd=source,env=env,text=True) for k in ('cargo','rustc')}
pins.update(cargo_sha256=digest(sdk/'bin/cargo'),rustc_sha256=digest(sdk/'bin/rustc'),
            sources={n:digest(source/n) for n in files})
(dest/'inputs.json').write_text(json.dumps(pins,indent=2)+'\n')
rows=[]
def visit(arm,label,flag,evict=False):
    store,product=dest/('build-'+arm),dest/('target-'+arm)
    key=arm+'-'+label
    od=dest/'logs'/key;od.mkdir()
    ex=None
    if evict:
        [f]=[p for top in (store,product) for p in top.rglob('bin-consumer') if p.parent.name=='fingerprint' or p.parent.parent.name=='.fingerprint']
        assert f.is_file() and f.stat().st_size==16
        ex=[f.relative_to(dest).as_posix(),digest(f)]
        f.rename(dest/'escrow'/key)
    args=['cargo','+ohm']+([] if flag=='default' else ['-Zrelink-only='+flag])+['build','--offline','-j2','-p','consumer','--message-format=json']
    e=dict(env,CARGO_TARGET_DIR=str(product),CARGO_BUILD_BUILD_DIR=str(store))
    trace=['strace','-ff','-qq','-s','64000','-e','trace=execve','-o',str(od/'exec')]
    with (od/'stdout').open('wb') as out,(od/'stderr').open('wb') as err:
        proc=subprocess.run(trace+args,env=e,cwd=source,stdout=out,stderr=err,timeout=60)
    msgs=[json.loads(l) for l in (od/'stdout').read_bytes().splitlines()]
    assert proc.returncode in (0,101) and msgs[-1].get('reason')=='build-finished' and msgs[-1]['success']==(proc.returncode==0), key
    events=[line for f in od.glob('exec.*') for line in f.read_text().splitlines() if line.startswith('execve(') and line.endswith('= 0')]
    roots=[l for l in events if 'bin/rustc"' in l[:l.index(', [')] and '"--crate-name", "consumer"' in l]
    links=[l for l in events if 'rust-lld"' in l[:l.index(', [')] or 'wild"' in l[:l.index(', [')] or 'ld.lld"' in l[:l.index(', [')]]
    errors=[]
    for m in msgs:
        if m['reason']=='compiler-message' and m['message']['level']=='error':
            error=m['message'];errors.append((error['message'],[(p['file_name'],p['line_start'],p['column_start']) for p in error['spans'] if p['is_primary']]))
    observed=shutil.which('cargo',path=env['PATH']); assert observed
    runtime=None;elf=None
    if proc.returncode==0:
        binary=product/'debug/consumer'
        runtime=subprocess.check_output([binary],env=e,text=True).strip();elf=digest(binary)
        assert runtime=='17' and not errors
    if proc.returncode==101:
        assert errors and any(x[0]=='link recipe was not requested' and x[1] for x in errors), (key,errors)
    row=dict(arm=arm,label=label,flag=flag,exit=proc.returncode,dirty=[m['target']['name'] for m in msgs if m['reason']=='compiler-artifact' and not m['fresh']],runtime=runtime,elf=elf,root_rustc=len(roots),root_emit=[('"emit-rlink"' in l or '"-Zemit-rlink"' in l) for l in roots],native_linker_processes=len(links),errors=errors,evicted_short_fingerprint=ex,raw={p.name:digest(p) for p in sorted(od.iterdir())})
    rows.append(row);(dest/'rows.json').write_text(json.dumps(rows,indent=2)+'\n')
    print(arm,label,flag,proc.returncode,len(roots),row['root_emit'],runtime,flush=True)


for arm,positive in [('implicit','default'),('explicit','yes')]:
    visit(arm,'start',positive)
    visit(arm,'unchanged',positive)
    visit(arm,'switch','no')
    visit(arm,'switch-repeat','no')
    if rows[-1]['exit']==0:
        visit(arm,'evict-cargo-fingerprint','no',evict=True)
    visit(arm,'restore',positive)
    visit(arm,'restore-repeat',positive)
visit('empty','no','no')
visit('empty','repeat','no')
visit('empty','recover','default')
assert {n:digest(source/n) for n in files}==pins['sources']
(dest/'terminal.json').write_text(json.dumps(dict(inputs=digest(dest/'inputs.json'),rows=digest(dest/'rows.json'),visits=len(rows)),indent=2)+'\n')
