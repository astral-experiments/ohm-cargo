"""Check that genuine file text and remappings remain observable across a cached derive."""
from pathlib import Path
import hashlib, json, os, subprocess, sys

base=Path('/mnt/devbox-scratch/dev-user/ohm-whole-skips-20261027')
driver=Path(sys.argv[1]); label=sys.argv[2]; sdk=base/'frozen-toolchain'
out=base/'mixed-registry-only-pilot'/('macro-real-path-control-'+label)
out.mkdir(mode=0o700); src=out/'sources';src.mkdir()
def sha(p):
    with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def dump(p,x):p.write_text(json.dumps(x,indent=2,sort_keys=True)+'\n')
def invoke(name,argv):
    row=out/name;row.mkdir()
    ns=['bwrap','--ro-bind','/','/','--dev','/dev','--proc','/proc','--tmpfs','/tmp','--bind',str(out),str(out),'--ro-bind',str(driver),str(sdk/'lib/librustc_driver-774a793a844d5500.so'),'--chdir',str(out),'--']
    cfg=dict(os.environ,RUSTUP_HOME=str(base/'rustup'),RUSTUP_AUTO_INSTALL='0')
    p=subprocess.run([*ns,*map(str,argv)],env=cfg,capture_output=True)
    (row/'stdout').write_bytes(p.stdout);(row/'stderr').write_bytes(p.stderr)
    dump(row/'receipt.json',dict(argv=list(map(str,argv)),returncode=p.returncode))
    assert not p.returncode,(argv,p.stderr[-1200:]);return p
(src/'maker.rs').write_text('''extern crate proc_macro;
use proc_macro::{Literal, TokenStream, TokenTree};
#[proc_macro_derive(Parse)]
pub fn parse(_: TokenStream) -> TokenStream {
    eprintln!("actually ran derive");
    let _ = "314159".parse::<TokenStream>().unwrap();
    TokenStream::new()
}
#[proc_macro]
pub fn show(input: TokenStream) -> TokenStream {
    let span = input.into_iter().next().unwrap().span();
    let local = span.local_file().unwrap();
    let value = format!("{}|{}|{}", span.source_text().unwrap(), span.file(), local.file_name().unwrap().to_str().unwrap());
    TokenTree::Literal(Literal::string(&value)).into()
}
''')
(src/'main.rs').write_text('#[derive(maker::Parse)] pub struct Marker;\ninclude!("late.rs");\nfn main() { println!("{}", show()); }\n')
compiler=['rustc','+ohm','--edition=2024']
invoke('make-plugin',[*compiler,src/'maker.rs','--crate-type=proc-macro','--crate-name','maker','-o',out/'libmaker.so'])
rows={}
for label,token,remap,inc in [('initial','original_token','alpha','warm'),('changed','updated_token','alpha','warm'),('cold','updated_token','alpha','empty'),('remapped','updated_token','beta','warm'),('cold-remapped','updated_token','beta','empty-remapped')]:
    (src/'late.rs').write_text("fn show() -> &'static str { maker::show!("+token+") }\n")
    p=invoke(label,[*compiler,src/'main.rs','--extern','maker='+str(out/'libmaker.so'),'-Cincremental='+str(out/inc),'-Zcache-proc-macros','-Zpublic-api-hash','--remap-path-prefix',str(src)+'=/'+remap,'-o',out/'app'])
    value=invoke('run-'+label,[out/'app']).stdout.decode().strip();expected=f'{token}|/{remap}/late.rs|late.rs'
    rows[label]=dict(expected=expected,observed=value,derive_executed=b'actually ran derive' in p.stderr)
    dump(out/'results.json',rows);assert value==expected,(label,expected,value)
assert rows['initial']['derive_executed'] and not rows['changed']['derive_executed'] and rows['cold']['derive_executed']
dump(out/'complete.json',dict(driver_sha256=sha(driver),frontend_sha256=sha(sdk/'bin/rustc'),runtimes=len(rows),results_sha256=sha(out/'results.json')))
