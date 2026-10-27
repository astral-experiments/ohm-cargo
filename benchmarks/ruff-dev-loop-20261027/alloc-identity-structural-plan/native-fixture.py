"""Exercise incremental literal identity and distinct allocation provenance on a real release compiler."""
from pathlib import Path
import hashlib, json, os, re, shutil, socket, subprocess, sys

p=Path('/mnt/devbox-scratch/dev-user/ohm-whole-skips-20261027')
root=p/'alloc-retained-literal-v1'
arm,=sys.argv[1:]
assert socket.gethostname()=='charlie-ohm-loader-perf-1024' and arm in ('parent','candidate')
os.sched_setaffinity(0,{28,29});os.nice(8)
sdk=p/'frozen-toolchain';r=sdk/'lib/librustc_driver-774a793a844d5500.so'
image=p/('parse-source-replay-v3' if arm=='parent' else 'parse-source-alloc-replay-v1')/'candidate-driver.so'
def h(f):
    with Path(f).open('rb') as s:return hashlib.file_digest(s,'sha256').hexdigest()
def write(f,x):f.write_text(json.dumps(x,indent=2,sort_keys=True)+'\n')
assert h(image)==(image.parent/'verified.sha').read_text().split()[0]
parent='36d1fd142355c3ad9e0ce006c1e92b7e511cba70c431b09eb1e335f572d27d05'
assert (h(image)==parent)==(arm=='parent') and h(sdk/'bin/rustc')=='4fa9a18b77430bcc416e88561b6fe5797d98b996a7698b9f3bd11d4e7817a19f'
root.mkdir(mode=0o700,exist_ok=True);visible=root/'visible';visible.mkdir(exist_ok=True)
out=root/arm;out.mkdir(mode=0o700);assert shutil.disk_usage(root).free>25<<30
env={'HOME':str(Path.home()),'PATH':str(Path.home()/'.cargo/bin')+':/usr/bin:/bin','LANG':'C.UTF-8','LC_ALL':'C.UTF-8','RUSTUP_HOME':str(p/'rustup'),'RUSTUP_AUTO_INSTALL':'0','RUSTC_BOOTSTRAP':'1'}
def run(st,d,args):
    d.mkdir(parents=True);write(d/'argv.json',args)
    ns=['bwrap','--die-with-parent','--ro-bind','/','/','--dev','/dev','--proc','/proc','--tmpfs','/tmp','--bind',str(st),str(visible),'--ro-bind',str(image),str(r),'--chdir',str(visible/'src'),'--']
    z=subprocess.run([*ns,*args],env=env,capture_output=True,timeout=90)
    (d/'stdout').write_bytes(z.stdout);(d/'stderr').write_bytes(z.stderr);write(d/'status.json',{'returncode':z.returncode});return z
rust=['rustc','+ohm','--sysroot',str(sdk),'--edition=2024']
literal="""#![crate_type="rlib"]
#[inline] pub fn left() -> (&'static str, u32) { ("a long repeated string from the same module", 1) }
#[inline] pub fn right() -> (&'static str, u32) { ("a long repeated string from the same module", VALUE) }
pub fn observed() -> u32 { assert_eq!(left().0, right().0); right().1 }
"""
unique="""#![crate_type="rlib"]
#![feature(core_intrinsics, const_heap)]
#![allow(internal_features)]
const fn heap() -> &'static [u8; 8] {
    unsafe {
        let p = core::intrinsics::const_allocate(8, 1) as *mut [u8; 8];
        *p = *b"abcdefgh";
        &*(core::intrinsics::const_make_global(p.cast()) as *const [u8; 8])
    }
}
pub const ALLOC: &[u8; 8] = heap();
pub const LITERAL: &[u8; 8] = b"abcdefgh";
pub static FIRST: [u8; 8] = *b"abcdefgh";
pub static SECOND: [u8; 8] = *b"abcdefgh";
#[inline] pub fn left() -> &'static [u8; 8] { ALLOC }
#[inline] pub fn right() -> (&'static [u8; 8], u32) { (LITERAL, VALUE) }
pub fn observed() -> u32 {
    assert_eq!(left(), right().0);
    assert!(!core::ptr::eq(&FIRST, &SECOND));
    right().1
}
REJECT
"""
bad='const _: isize = unsafe { ALLOC.as_ptr().offset_from(LITERAL.as_ptr()) };'
sources={'literal':literal,'separate':unique,'separate-offset':unique}
def source(kind,v):
    return sources[kind].replace('VALUE',str(v)).replace('REJECT',bad if kind=='separate-offset' and v==8 else '')
results={}
for kind in sources:
    case=out/kind;case.mkdir()
    for instrumentation in ('plain','stats'):
        rows={};group=case/instrumentation;group.mkdir()
        for label,cache,value in [('train','retained',7),('warm','retained',8),('empty','empty',8),('second-empty','second-empty',8),('restore','retained',7),('clean-original','clean-original',7)]:
            st=group/cache
            for n in ('src','out','inc'):(st/n).mkdir(parents=True,exist_ok=True)
            for n in ('libprobe.rlib','libprobe.rmeta'):
                f=st/'out'/n
                if f.exists():assert f.is_file() and not f.is_symlink();f.unlink()
            evidence=group/'evidence'/label;evidence.mkdir(parents=True)
            tx=source(kind,value);(st/'src/probe.rs').write_text(tx);(evidence/'probe.rs').write_text(tx)
            cmd=[*rust,'--crate-name','probe','--emit=link,metadata','--error-format=json','-Copt-level=1','-Cdebuginfo=2','-Ccodegen-units=16','-Cincremental='+str(visible/'inc'),*(['-Zmeta-stats'] if instrumentation=='stats' else []),'probe.rs','--out-dir',str(visible/'out')]
            res=run(st,evidence/'compile',cmd)
            diags=[json.loads(l) for l in res.stderr.splitlines() if l.startswith(b'{"')]
            e0080=[d for d in diags if (d.get('code') or {}).get('code')=='E0080']
            error=kind=='separate-offset' and value==8
            assert res.returncode==int(error),(kind,instrumentation,label,res.returncode,res.stderr[-1300:])
            row={'value':value,'returncode':res.returncode,'source_sha256':h(evidence/'probe.rs'),'diagnostics_codes':[(d.get('code') or {}).get('code') for d in diags if d.get('level')=='error']}
            if error:
                assert len(e0080)==1 and b'offset' in res.stderr.lower() and b'allocat' in res.stderr.lower() and not (st/'out/libprobe.rmeta').exists(),res.stderr[-1500:]
                row['error_message']=e0080[0]['message']
            else:
                for n in ('libprobe.rlib','libprobe.rmeta'):
                    fr=st/'out'/n;assert fr.is_file();shutil.copy2(fr,evidence/n);row[n]=h(fr)
                hd=run(st,evidence/'header',[*rust,'-Zls=root',str(visible/'out/libprobe.rmeta')]);assert hd.returncode==0
                row['private']=re.search(rb'private hash ([0-9a-f]+)',hd.stdout).group(1).decode()
                row['stats']={m[1]:int(m[2].replace(',','').replace('_','')) for line in res.stderr.decode().splitlines() if (m:=re.fullmatch(r'meta-stats\s+(.+?)\s+([0-9,_]+)\s+\(\s*[0-9.]+%\)',line))}
            rows[label]=row
        results[kind+'/'+instrumentation]=rows
    if kind!='separate-offset':
        st=case/'clients'
        for n in ('src','offered','bridge','images'):(st/n).mkdir(parents=True,exist_ok=True)
        (st/'src/bridge.rs').write_text('extern crate probe; pub fn from_bridge() -> u32 { probe::observed() }\n')
        (st/'src/caller.rs').write_text('extern crate bridge; extern crate probe; fn main() { println!("{}:{}", bridge::from_bridge(), probe::observed()); }\n')
        for built in ('warm','empty'):
            shutil.copy2(case/'plain/evidence'/built/'libprobe.rlib',st/'offered/libprobe.rlib')
            br=run(st,case/'readers'/('bridge-'+built),[*rust,'--crate-name','bridge','--crate-type=rlib','bridge.rs','--extern','probe='+str(visible/'offered/libprobe.rlib'),'-o',str(visible/'bridge/libbridge.rlib')]);assert br.returncode==0,br.stderr
            for provided in ('warm','empty'):
                shutil.copy2(case/'plain/evidence'/provided/'libprobe.rlib',st/'offered/libprobe.rlib')
                ev=case/'readers'/(built+'-'+provided);args=[*rust,'caller.rs','--extern','bridge='+str(visible/'bridge/libbridge.rlib'),'--extern','probe='+str(visible/'offered/libprobe.rlib'),'-L','dependency='+str(visible/'offered'),'-o',str(visible/'images/app')]
                bp=run(st,ev/'compile',args);assert bp.returncode==0,bp.stderr
                n=run(st,ev/'native',[str(visible/'images/app')]);assert n.returncode==0 and n.stdout==b'8:8\n'
                write(ev/'bindings.json',{'rlib':h(st/'offered/libprobe.rlib'),'bridge':h(st/'bridge/libbridge.rlib'),'elf':h(st/'images/app')})
    write(out/'results.json',results)
opening={}
for k,rows in results.items():
    if k.endswith('/stats'):
        plain=results[k.rsplit('/',1)[0]+'/plain']
        eq=all(v.get('libprobe.rmeta')==plain[name].get('libprobe.rmeta') for name,v in rows.items())
        opening[k]={'stats_reproduced_plain':eq,'warm_empty_equal':rows['warm'].get('libprobe.rmeta')==rows['empty'].get('libprobe.rmeta'),'counts':[rows[n].get('stats',{}).get('interpret-alloc-index') for n in ('warm','empty','second-empty')],'expected_rejections':[rows[n]['returncode'] for n in ('warm','empty','second-empty')]}
write(out/'done.json',{'driver':h(image),'rustc':h(sdk/'bin/rustc'),'timed_observations':0,'outcomes':opening,'native_callers':8})
print(json.dumps(opening,sort_keys=True))
