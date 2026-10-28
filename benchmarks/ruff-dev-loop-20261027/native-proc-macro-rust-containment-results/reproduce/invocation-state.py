"""Compare per-process static macro state across four distinct native invocations."""
from pathlib import Path
import hashlib,json,os,subprocess,sys
root=Path(sys.argv[1]);root.mkdir();sdk=Path(sys.argv[2]);code='''#![crate_type="proc-macro"]
extern crate proc_macro;
use proc_macro::TokenStream;
use std::sync::atomic::{AtomicUsize, Ordering};
static NEXT: AtomicUsize = AtomicUsize::new(1);
fn next(kind: &str, at: &str) -> usize {
    let n = NEXT.fetch_add(1, Ordering::SeqCst); eprintln!("{kind} {at} {n}"); n
}
#[proc_macro_derive(Native)] pub fn derive(input: TokenStream) -> TokenStream {
    let s = input.to_string(); let name = s.split_whitespace().nth(1).unwrap().trim_end_matches(';');
    let n = next("derive", name); format!("impl {name} {{ const N: usize = {n}; }}").parse().unwrap()
}
#[proc_macro_attribute] pub fn number(attr: TokenStream, _: TokenStream) -> TokenStream {
    let name = attr.to_string(); let n = next("attr", &name); format!("const {name}: usize = {n};").parse().unwrap()
}
''';reader='''#[macro_use] extern crate macro_impl;
#[derive(Native)] struct Left;
#[number(FIRST)] fn a() {}
#[derive(Native)] struct Right;
#[number(SECOND)] fn b() {}
fn main() { println!("{} {} {} {}", Left::N, FIRST, Right::N, SECOND); }
''';(root/'macro_impl.rs').write_text(code);(root/'reader.rs').write_text(reader)
r=root/'rustup/toolchains';r.mkdir(parents=True);(r/'ohm').symlink_to(sdk);env=dict(HOME=str(root),RUSTUP_HOME=str(r.parent),RUSTUP_AUTO_INSTALL='0',PATH='/home/dev-user/.cargo/bin:/usr/bin:/bin',LANG='C.UTF-8');call=lambda a:subprocess.run(a,cwd=root,env=env,text=True,capture_output=True,timeout=60,check=True);assert Path(call(['rustc','+ohm','--print','sysroot']).stdout.strip()).samefile(sdk);call(['rustc','+ohm','macro_impl.rs']); h=lambda p:hashlib.file_digest(p.open('rb'),'sha256').hexdigest();rows={}
for mode in ['same-thread','cross-thread']:
 for setting in ['yes','no']:
  for phase in ['cold','warm']:
   command=['rustc','+ohm','reader.rs','--extern','macro_impl=libmacro_impl.so','-Zcache-proc-macros='+setting,'-Zproc-macro-execution-strategy='+mode,'-C','incremental='+mode+setting,'-o','reader'];x=call(command); y=call(['./reader']);ns=[int(z) for z in y.stdout.strip().split()];assert sorted(ns)==[1,2,3,4];rows['-'.join((mode,setting,phase))]=dict(argv=command,exit=x.returncode,stderr=x.stderr.splitlines(),value=ns,exe_sha=h(root/'reader'))
sdksha=h(next((sdk/'lib').glob('librustc_driver-*.so')));rec={'rows':rows,'driver':sdksha,'rustc':h(sdk/'bin/rustc'),'source':{n:h(root/n) for n in ['macro_impl.rs','reader.rs']}};(root/'terminal.json').write_text(json.dumps(rec,sort_keys=True,indent=2)+'\n')
