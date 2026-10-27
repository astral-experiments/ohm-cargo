"""Reorder source files ahead of an exported macro and decode its generated MIR in a later untouched Rust caller."""
from pathlib import Path
import sys
helper=Path(__file__).resolve().with_name('common-guards.py')
exec(compile(helper.read_text().split('stages=')[0].replace("'0-3'","'20-23'"),str(helper),'exec'))
defs=main/'leaf/src/macros.rs'
defs.write_text('''#[macro_export] macro_rules! generate {
    () => {
        #[inline(never)]
        pub fn ratio<T>(_: T, x: i32) -> i32 { 21 / x }

        #[inline(never)]
        pub fn nested<T>(_: T, x: i32) -> i32 {
            $crate::indirect(x)
        }
    };
}
''')
for i in range(9):
 (main/f'leaf/src/p{i}.rs').write_text('const _: () = ();\n')
def src(active):
 return ''.join(f'#[cfg({"all" if active else "any"}())] mod p{i};\n' for i in range(9))+'''mod macros;
pub fn value() -> i32 { 43 }
#[inline(never)] pub fn indirect(x: i32) -> i32 { 42 / x }
'''
bundle.write_text('''leaf::generate!();
#[unsafe(no_mangle)] pub extern "C" fn observed() -> i32 { 42 }
pub fn via_rust() -> i32 { observed() }
''')
(main/'app/src/main.rs').write_text('''#[derive(Debug)] struct Caller;
fn main(){
    std::panic::set_hook(Box::new(|x| {
        let loc=x.location().unwrap();
        println!("{}:{}:{}",loc.file(),loc.line(),loc.column());
    }));
    let _=std::panic::catch_unwind(|| bundle::ratio(Caller, std::hint::black_box(0)));
    let _=std::panic::catch_unwind(|| bundle::nested(Caller, std::hint::black_box(0)));
}
''')
rows=[]
def caller(r):
 if (target/'debug/app').exists():
  for f in target.rglob('out/app-*'):
   if f.is_file() and os.access(f,os.X_OK): f.rename(r.parent/(f.name+'.'+r.name+'.old'))
 out,child=run(r,'app');assert all(x['crate']!='bundle' for x in child)
 assert [x['link_only'] for x in child if x['crate']=='app']==[False],(r,child)
 p=Path(out['app']['executable']);return {'output':sp.check_output([p],text=True).splitlines(),'executable':sha(p)}
for tag,active in [('before',False),('add_files_before_macro',True),('remove_files_before_macro',False)]:
 rec=root/tag;leaf.write_text(src(active));out,kids=run(rec/'current','bundle');mode=[k['link_only'] for k in kids if k['crate']=='bundle'];assert len(mode)==1
 so,actual=result(out); first=caller(rec/'current-caller')
 so.rename(rec/'pre-oracle.so');full,c=run(rec/'forced-full','bundle');assert [k['link_only'] for k in c if k['crate']=='bundle']==[False];_,gold=result(full);second=caller(rec/'full-caller')
 p=next(target.rglob('lib-leaf.public-api-hash'));h=json.loads(p.read_bytes())
 rows.append({'stage':tag,'first_library_linkonly':mode[0],'producer_hash':h,'library_equal':{k:actual[k]==gold[k] for k in actual},'current_consumer':first,'full_consumer':second})
 (root/'observations.json').write_text(json.dumps(rows,indent=2)+'\n');print(rows[-1],flush=True)
