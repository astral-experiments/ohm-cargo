"""Attempt a genuine native provider in the Ruff library, with unchanged bin harness source/flags."""
from pathlib import Path
import collections,hashlib,json,os,runpy,shutil,subprocess,sys
HERE=Path(__file__).resolve().parent
exec(compile((HERE/'replay-v2.py').read_text().split('guard();installed()')[0],str(HERE/'replay-v2.py'),'exec'))
guard();installed()
orig=(HERE/'replay-v2.py').read_text()
sc=globals();exec(compile(orig[orig.index('common_env='):orig.index('historical=')],__file__,'exec'),sc)
q=HERE/'provider';q.mkdir()
diag=A['PLAN']['path']; captured=C/'original.rs';extra=b"""
// Deliberate native provider for the standalone link-selection control.
#[cfg(all(target_os = "linux", target_arch = "x86_64"))]
#[unsafe(export_name = "write")]
unsafe extern "C" fn catch_native_write(_: i32, _: *const u8, _: usize) -> isize {
    unsafe extern "C" { fn _exit(status: i32) -> !; }
    unsafe { _exit(83) }
}
"""
src=q/'diagnostics.rs';src.write_bytes(captured.read_bytes())
# Use the untouched Ruff binary source throughout, including after the additional reader in v2.
ns=[*rootbind,'--ro-bind',str(src),str(SOURCE/diag),'--chdir',str(SOURCE),'--']
def run(call,step,prefix,expect=None):
    r=subprocess.run([*ns,*call],env=common_env,capture_output=True)
    (step/(prefix+'.out')).write_bytes(r.stdout);(step/(prefix+'.err')).write_bytes(r.stderr)
    (step/(prefix+'.status')).write_text(str(r.returncode)+'\n')
    if expect is not None:assert r.returncode==expect,(prefix,r.returncode,r.stderr[-1500:])
    return r
for st,changed in [('ordinary',False),('provider',True),('restored',False)]:
    step=q/st;step.mkdir();(step/'trace').mkdir()
    if changed:src.write_bytes(captured.read_bytes()+extra)
    elif st=='restored':src.write_bytes(captured.read_bytes())
    c=run(['strace','-ff','-q','-s','1048576','-e','trace=execve','-o',str(step/'trace/exec'),'cargo','+ohm','test','--no-run','-p','ruff_python_formatter','--locked','--offline','-j4','--message-format=json'],step,'cargo',0)
    vals=[json.loads(s) for s in c.stdout.splitlines()];rs=[v for v in vals if v['reason']=='compiler-artifact'];assert len(rs)==218
    f,=[Path(r['executable']) for r in rs if r['target']['kind']==['bin'] and r['profile']['test']]
    armnat=A['native'](step/'trace',SDK);put(step/'native.json',armnat)
    cmd=run([str(f),'--list'],step,'list')
    out=STATE/f.relative_to(D); source_elf=sha(out)
    l=[z for z in armnat['links'] if z['output']==str(f)]
    assert len(l)==1 or not l and st=='ordinary'
    m=[j for j in armnat['jobs'] if any(token in a for a in j['argv'])];assert len(m)<=1
    if l:
        lay=out.with_name(out.name+'.layout');shutil.copyfile(lay,step/'harness.layout')
    rf,=[Path(k) for r in rs if r['target']['name']=='ruff_formatter' for k in r['filenames'] if k.endswith('.rlib')]
    rfp=STATE/rf.relative_to(D)
    nm=subprocess.run(['nm','-D',out],capture_output=True);assert nm.returncode==0
    symbols=[x for x in nm.stdout.decode().splitlines() if x.strip().endswith(' write') or ' write@GLIBC' in x]
    source_rows={'step':st,'source':sha(src),'harness_root':sha(SOURCE/'crates/ruff_python_formatter/src/main.rs'),'cargo':A['TOOLS']['cargo'],'n':len(rs),'rustc':collections.Counter(j['kind'] for j in armnat['jobs']),'wild_count':len(armnat['links']),'harness_rustc':m[0]['kind'] if m else 'absent','harness_ld':l[0]['raw'] if l else None,'harness_status':cmd.returncode,'harness_output':cmd.stdout.decode(),'raw_elf':source_elf,'rlink':sha(next(out.parent.glob('*.rlink'))),'archive':sha(rfp),'write_symbol':symbols}
    if l:
        parts=api=runpy.run_path(str(HERE/'linked-layout.py'));files,_=api['decode_layout']((step/'harness.layout').read_bytes())
        source_rows['selected_formatter_members']=[e[-1] for n,e,s,t in files if Path(n).name==rf.name and e]
    put(step/'row.json',source_rows)
    print(st,source_rows['rustc'],source_rows['harness_rustc'],len(source_rows.get('selected_formatter_members',[])),cmd.returncode,repr(cmd.stdout[:80]),symbols,source_elf[:13],flush=True)
put(q/'complete.json',{'phases':3,'observed':[json.loads((q/t/'row.json').read_bytes())['harness_status'] for t in ('ordinary','provider','restored')]})
