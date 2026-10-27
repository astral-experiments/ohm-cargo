"""Copy only the diagnostic program, observations, selected binary instructions, and symbol resolutions."""
from pathlib import Path
import hashlib,gzip,json,subprocess
P=Path('/mnt/devbox-scratch/dev-user/ohm-whole-skips-20261027');J=P/'mixed-registry-only-pilot';X=Path.home()/'.cache/ohm-233-position-qualified-20261027';S=X/'mixed-registry-seed-programs-20261027'
out=P/'parser-private-source-ids-export';out.mkdir(mode=0o700)
def put(src,name):
    src=Path(src);dst=out/name;assert src.is_file() and not src.is_symlink()
    b=src.read_bytes()
    if len(b)>80_000:dst=Path(str(dst)+'.gz');b=gzip.compress(b,6,mtime=0)
    assert not dst.exists();dst.parent.mkdir(parents=True,exist_ok=True);dst.write_bytes(b)
def dump(n,x):
    p=out/n;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(x,sort_keys=True,indent=2)+'\n')
def sha(p):
    with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
for p in ['observe-frozen-metavars.c','probe-original-driver.py','probe-sorted-source-ids.py','observe-frozen-source-ids.c','probe-sorted-source-ids-v2.py','observe-frozen-source-ids-v2.c','observe-source-acquisition.c','probe-source-acquisition.py','collect-rustc-source-map.py']:
    put(S/p,'programs/'+p)
for name in ['native-private-hash-readback','native-source-ids-readback','native-source-ids-readback-v2','native-source-acquisition']:
    base=J/name
    for nm in ['probe.json','results.json','complete.json','caller.disasm','input-flags.json','source-id-difference.json']:
        if(base/nm).exists():put(base/nm,name+'/'+nm)
    for hist in ['all','empty']:
        d=base/hist
        for nm in ['raw.jsonl','files.jsonl','stdout','stderr','acquire.jsonl','rmeta.root.txt','acquisition-coverage.json']:
            if(d/nm).exists():put(d/nm,name+'/'+hist+'/'+nm)
for pat in ['parser-source-id-v2.*','parser-source-acquisition.std*','parser-native-probe.std*','parser-source-ids.std*']:
    for f in S.glob(pat):
        if f.suffix in {'.stdout','.stderr'}:put(f,'logs/'+f.name)
drv=X/'drivers/driver-dec72d1e68fdb0f8ff91fc98e8a826bf837878eca30b1ec5ea2f3258b6b2f99f'
work=J/'native-source-acquisition';d=work/'empty';opts=json.loads((work/'input-flags.json').read_bytes())['argv']
q=next(p.split('=',1)[1] for p in opts if p.startswith('get_size_derive2='));unit=d/'physical/target'/Path(q).relative_to(P/'native-target')
assert unit.is_file()
rows=[json.loads(z) for z in (d/'acquire.jsonl').read_text().splitlines()]
hot=[z for z in rows if 'frames' in z]; assert hot
arm_so=unit.name; all_frames={tuple(f) for z in hot for f in z['frames'] if f[0] in (arm_so,'librustc_driver-774a793a844d5500.so')}
def syms(lib,pcs):
    addresses=sorted({pc for img,pc in all_frames if img==lib.name or (lib==drv and img.startswith('librustc_driver-'))})
    lookup=subprocess.run(['addr2line','-C','-f','-e',str(lib),*[hex(int(a,16)-1) for a in addresses]],capture_output=True,check=True,text=True).stdout.splitlines()
    assert len(lookup)==2*len(addresses)
    return {pc:{'symbol':lookup[2*i],'source':lookup[2*i+1]} for i,pc in enumerate(addresses)}
dump('backtrace/symbols.json',{'actual_driver':{'sha256':sha(drv),'frames':syms(drv,all_frames)},'proc_macro':{'sha256':sha(unit),'logical_path':q,'frames':syms(unit,all_frames)}})
for which,lo,hi in [('crate-hash',0x5d83180,0x5d8422c),('source-name-kind',0x6a03940,0x6a03983),('source-insert',0x6a03800,0x6a038ba),('from-str',0x6a035a0,0x6a03720)]:
    data=subprocess.run(['objdump','-dC',f'--start-address={hex(lo)}',f'--stop-address={hex(hi)}',str(drv)],check=True,capture_output=True).stdout
    p=out/'backtrace'/(which+'.disasm');p.write_bytes(data)
print(out,sum(p.stat().st_size for p in out.rglob('*') if p.is_file()))
