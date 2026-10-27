"""Verify shared-monomorphization, transitively loaded code and constructor roots in a mixed cdylib/rlib."""
from pathlib import Path
import sys
case=sys.argv.pop(1)
basepath=Path(__file__).resolve().with_name('common-guards.py')
exec(compile(basepath.read_text().split("stages=")[0].replace("'0-3'","'20-23'"),str(basepath),'exec'))
mleaf=main/'leaf/Cargo.toml';mbundle=main/'bundle/Cargo.toml';original_toml=mbundle.read_text();env['RUSTC_BOOTSTRAP']='1'
if case=='mono':
    mleaf.write_text(mleaf.read_text()+'[dependencies]\nmid={ path="../mid" }\n')
    mid.write_text('#[inline(never)] pub fn shared<T>() -> i32 { core::mem::size_of::<T>() as i32 }\n')
    bundle.write_text('#[unsafe(no_mangle)] pub extern "C" fn observed()->i32 { leaf::value() + mid::shared::<u128>() }\npub fn via_rust()->i32 { observed() }\n')
    source='#[inline(never)] pub fn value()->i32 { private() }\nfn private()->i32 { mid::shared::<TY>() }\n'
    stages=[('original',source.replace('TY','u128'),32),('remove_u128',source.replace('TY','u64'),24),('restore_u128',source.replace('TY','u128'),32)]
elif case=='load':
    mleaf.write_text(mleaf.read_text()+'[dependencies]\nmid={ path="../mid" }\n')
    mbundle.write_text(original_toml.replace('mid={path="../mid"}\n',''))
    mid.write_text('#[inline(never)] pub fn secret()->i32 { 9 }\n')
    bundle.write_text('#[unsafe(no_mangle)] pub extern "C" fn observed()->i32 { leaf::value() }\npub fn via_rust()->i32 { observed() }\n')
    source='#[inline(never)] pub fn value()->i32 { private() }\nfn private()->i32 { BODY }\n'
    stages=[('original',source.replace('BODY','7'),7),('load_transitive',source.replace('BODY','mid::secret()'),9),('unload_transitive',source.replace('BODY','7'),7)]
elif case=='init':
    bundle.write_text('#[unsafe(no_mangle)] pub extern "C" fn observed()->i32 { leaf::value() }\npub fn via_rust()->i32 { observed() }\n')
    source='''#![allow(dead_code)]
use std::sync::atomic::{AtomicI32, Ordering};
static COUNTER: AtomicI32 = AtomicI32::new(0);
extern "C" fn one(){ COUNTER.store(101, Ordering::SeqCst); }
extern "C" fn two(){ COUNTER.store(202, Ordering::SeqCst); }
#[used]
#[unsafe(link_section=".init_array")]
static TAG: extern "C" fn() = PICK;
#[inline(never)] pub fn value()->i32 { COUNTER.load(Ordering::SeqCst) }
'''
    stages=[('original',source.replace('PICK','one'),101),('switch_initializer',source.replace('PICK','two'),202),('rename_retained',source.replace('TAG','NEW').replace('PICK','two'),202),('restore',source.replace('PICK','one'),101)]
elif case=='tls':
    bundle.write_text('#[unsafe(no_mangle)] pub extern "C" fn observed()->i32 { leaf::value() }\npub fn via_rust()->i32 { observed() }\n')
    source='''#![feature(thread_local)]
#[used]
PLACE
static PRIVATE: i32 = VALUE;
#[inline(never)] pub fn value()->i32 { PRIVATE }
'''
    stages=[('original',source.replace('PLACE','').replace('VALUE','9'),9),('turn_tls',source.replace('PLACE','#[thread_local]').replace('VALUE','10'),10),('restore',source.replace('PLACE','').replace('VALUE','9'),9)]
else:raise ValueError(case)
observations=[]
for tag,txt,val in stages:
    leaf.write_text(txt);rec=root/tag
    current,child=run(rec/'current','bundle')
    methods=[k['link_only'] for k in child if k['crate']=='bundle'];assert len(methods)==1,(tag,child)
    p=next(target.rglob('lib-leaf.public-api-hash'));h=json.loads(p.read_bytes());so,actual=result(current)
    assert actual['observed']==val,(tag,actual,val)
    out=current['leaf']['filenames'];p=next(Path(f) for f in out if f.endswith('.rlib'))
    symbols=sp.run(['nm','-AgC',str(p)],capture_output=True,text=True,check=True).stdout
    if case=='mono':
        found=[x.split(':')[-1].strip() for x in symbols.splitlines() if 'mid::shared::<' in x]
    elif case in ['init','tls']:
        found=[x.split(':')[-1].strip() for x in symbols.splitlines() if 'leaf::TAG' in x or 'leaf::NEW' in x or 'leaf::PRIVATE' in x]
    else:found=[x.split(':')[-1].strip() for x in symbols.splitlines() if 'mid::secret' in x]
    (rec/'leaf.nm').write_text(symbols)
    so.rename(rec/'pre-oracle.so');full,children=run(rec/'forced-full','bundle');assert [k['link_only'] for k in children if k['crate']=='bundle']==[False]
    _,gold=result(full);checked={k:actual[k]==gold[k] for k in actual};assert gold['observed']==val
    observations.append({'stage':tag,'cargo_mixed_mode':'link-only' if methods[0] else 'full','expected':val,'current':actual['observed'],'forced_full':gold['observed'],'producer_hash':h,'observed_symbol':found,'field_equality':checked,'current_so':actual['sha256'],'forced_full_so':gold['sha256']})
    print(tag,observations[-1],flush=True);(root/'observations.json').write_text(json.dumps(observations,indent=2)+'\n')
