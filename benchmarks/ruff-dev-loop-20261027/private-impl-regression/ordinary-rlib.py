"""Scope the source-table failure to compiler heads and existing ordinary rlib early cutoff."""
from pathlib import Path
import sys
case=sys.argv.pop(1);helper=Path(__file__).resolve().with_name('common-guards.py')
exec(compile(helper.read_text().split('stages=')[0].replace("'0-3'","'20-23'"),str(helper),'exec'))
env['CARGO_INCREMENTAL']='1'
m=main/'bundle/Cargo.toml';m.write_text(m.read_text().replace('crate-type=["cdylib","rlib"]','crate-type=["rlib"]').replace('mid={path="../mid"}\n',''))
m=main/'Cargo.toml';m.write_text(m.read_text()+'\n[profile.dev]\nopt-level=1\ndebug="line-tables-only"\nlto="off"\n')
a=main/'app/src/main.rs'
a.write_text('''#[derive(Debug)] struct External;
fn main() {
    std::panic::set_hook(Box::new(|x| {let h=x.location().unwrap();println!("{}:{}:{}",h.file(),h.line(),h.column());}));
    let _=std::panic::catch_unwind(|| bundle::ratio(External,std::hint::black_box(0)));
    let _=std::panic::catch_unwind(|| bundle::nested(External,std::hint::black_box(0)));
    println!("{}",bundle::Public{x:7}.x);
}
''')
if case.startswith('exported_macro'):
 (main/'leaf/src/defs.rs').write_text('''#[macro_export] macro_rules! make {
    () => { #[inline(never)] pub fn ratio<T>(_:T,x:i32)->i32 { 21/x }
            #[inline(never)] pub fn nested<T>(_:T,x:i32)->i32 { $crate::indirect(x) }
            pub struct Public {pub x:i32} };
}
''');bundle.write_text('leaf::make!();\n')
else:
 (main/'leaf/src/defs.rs').write_text('''pub struct Public { pub x:i32 }
#[inline(always)] pub fn gg<T>(_: T, x:i32) -> i32 { 21/x }
#[inline(always)] pub fn hh<T>(_: T, x:i32) -> i32 { crate::indirect(x) }
''');bundle.write_text('''pub use leaf::defs::*;
#[inline(never)] pub fn ratio<T>(v:T,x:i32)->i32 { gg(v,x) }
#[inline(never)] pub fn nested<T>(v:T,x:i32)->i32 { hh(v,x) }
''')
for i in range(9):(main/f'leaf/src/p{i}.rs').write_text('const _:() = ();\n')
def src(b):
 return '#![allow(dead_code)]\n'+''.join(f'#[cfg({"all" if b else "any"}())] mod p{i};\n'for i in range(9))+('mod' if case.startswith('exported_macro') else 'pub mod')+' defs;\n'+'''pub fn indirect(x:i32)->i32 { 42/x }
struct Local;
impl Iterator for Local {
    type Item = TYPE;
    fn next(&mut self)->Option<Self::Item> { None }
}
'''.replace('TYPE','i8' if b and case!='exported_macro_ref' else 'u8')
def bin_app(rec):
 if (target/'debug/app').exists():
  for f in target.rglob('out/app-*'):
   if f.is_file() and os.access(f,os.X_OK):f.rename(rec.parent/(f.name+'.'+rec.name+'.old'))
 # Explicitly starting from no app product guarantees a true downstream compile.
 try:out,ks=run(rec,'app')
 except RuntimeError:
  err=(rec/'stderr').read_text()
  return {'success':False,'ice':'missing source file'in err,'unexpected_panic':'unexpectedly panicked'in err,'stderr_sha':sha(rec/'stderr')}
 assert not any(x['crate']=='bundle'for x in ks) and any(x['crate']=='app' and not x['link_only']for x in ks),(rec,ks)
 exe=Path(out['app']['executable']);cp=sp.run([exe],capture_output=True,text=True);return {'success':True,'exit':cp.returncode,'out':cp.stdout.splitlines(),'elf':sha(exe)}
rec_list=[]
for tag,b in [('short',False),('long',True),('short_again',False)]:
 rec=root/tag;leaf.write_text(src(b))
 out,ks=run(rec/'bundle','bundle');h=json.loads(next(target.rglob('lib-leaf.public-api-hash')).read_bytes())
 meta=next(Path(f)for f in out['bundle']['filenames'] if f.endswith('.rmeta'));rlib=next(Path(f)for f in out['bundle']['filenames']if f.endswith('.rlib'))
 origmeta=sha(meta);shutil.copyfile(meta,rec/'cached.rmeta');orig_lib=sha(rlib);desired={k['crate']:k['link_only']for k in ks};native=bin_app(rec/'app')
 canonical_rlib=meta.with_suffix('.rlib');assert canonical_rlib.is_file();canonical_rlib.rename(rec/'cached.rlib')
 out,children=run(rec/'full-bundle','bundle');assert [k['link_only']for k in children if k['crate']=='bundle']==[False],(tag,children)
 shutil.copyfile(meta,rec/'full.rmeta');checked=bin_app(rec/'full-app');assert checked['success'],(tag,checked)
 rec_list.append({'stage':tag,'source':sha(leaf),'driver':sha(driver),'producer':h,'bundle_before':desired,'metadata_equal':origmeta==sha(meta),'metadata':[origmeta,sha(meta)],'rlib_equal':orig_lib==sha(rlib),'cached_app':native,'full_app':checked})
 (root/'ordinary.json').write_text(json.dumps(rec_list,indent=2)+'\n');print(tag,h,desired,'meta=',origmeta==sha(meta),'cached=',native['success'],'full=',checked['success'],flush=True)
