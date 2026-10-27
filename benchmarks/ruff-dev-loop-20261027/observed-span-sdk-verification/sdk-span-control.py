"""Observe a real SDK token through a public proc-macro API against same-size, same-mtime metadata."""
from pathlib import Path
import os,sys,shutil,subprocess
sys.path.insert(0,str(Path(__file__).resolve().parent))
import paired
s=paired.Study(paired.getargs())
a=s.init('trained')
b=s.init('cold')
proc_macro=r'''
#[proc_macro_attribute]
pub fn sdk_token(_attr:proc_macro::TokenStream,item:proc_macro::TokenStream)->proc_macro::TokenStream{
  let token=item.into_iter().find(|t|t.to_string()=="const").expect("thread_local! emits const");
  let span=token.span();
  let answer=format!("{} {} {span:?}",span.file(),span.line());
  format!("const FROM_STD: &str = {:?};",answer).parse().unwrap()
}
'''
app=r'''std::thread_local! {
    #[hold_probe::sdk_token]
    static SDK_KEY: usize = const { 0 };
}
fn main() { println!("{} {}",hold_shapes::count(),FROM_STD); }
'''
for store in (a,b):
    with (store/'src/hold_probe/src/lib.rs').open('a') as f:f.write(proc_macro)
    (store/'src/hold_direct/src/main.rs').write_text(app)
std=next((s.tc/'lib/rustlib/x86_64-unknown-linux-gnu/lib').glob('libstd-*.rmeta'))
old_path=b'library/std/src/thread/local.rs'
new_path=b'library/std/src/thread/local.xs'
old=std.read_bytes();assert len(old_path)==len(new_path) and old.count(old_path)==2
mutated=s.root/std.name;mutated.write_bytes(old.replace(old_path,new_path))
orig_stat=std.stat();os.chmod(mutated,orig_stat.st_mode&0o777);os.utime(mutated,ns=(orig_stat.st_atime_ns,orig_stat.st_mtime_ns))
normal=subprocess.run; swapped=False
def bind(cmd,*args,**kwargs):
    if swapped and 'bwrap' in cmd:
        cmd=list(cmd);where=cmd.index('--chdir');cmd[where:where]=['--ro-bind',str(mutated),str(std)]
    return normal(cmd,*args,**kwargs)
subprocess.run=bind
def run(store,binary,phase):
    return s.run(store,binary,phase,trace=True,packages=('hold_direct',),expect=False)
for i in range(4):
    before=run(a,'C',f'baseline-{i}')
    assert before['status']==0, before
assert not before['roster'] and before['readers'] and all(w['complete'] for w in before['readers'].values())
o=before['native_products']['hold_direct']['output'];assert old_path.decode() in o,o
swapped=True
warm=run(a,'C','warm-replaced-sdk')
cold=run(b,'P','empty-replaced-sdk')
assert warm['status']==cold['status']==0, (warm['status'],cold['status'])
new=warm['native_products']['hold_direct']['output']
assert new==cold['native_products']['hold_direct']['output'] and new==o.replace(old_path.decode(),new_path.decode()), (o,new,cold)
assert 'hold_direct' in {x['crate'] for x in warm['roster'] if x['mode']=='full'}
result={'exact_cargo':s.digest['C'],'driver':s.digest['driver'],'sdk_basename':std.name,'old_sha256':paired.sha(std),'new_sha256':paired.sha(mutated),
 'size_equal':orig_stat.st_size==mutated.stat().st_size,'mtime_equal':orig_stat.st_mtime_ns==mutated.stat().st_mtime_ns,
 'modified_occurrences':old.count(old_path),'before':o,'warm':new,'empty':cold['native_products']['hold_direct']['output'],
 'initial_warm_roster':before['roster'],'changed_roster':warm['roster']}
paired.log_json(s.logs/'causal.json',result);print(result)
