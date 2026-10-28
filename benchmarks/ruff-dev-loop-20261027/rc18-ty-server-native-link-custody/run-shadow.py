"""Replay an actual retained ty_server e2e rustc recipe, using read-only donor mounts."""
import collections
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import socket
import stat
import subprocess
import sys
import traceback

P = Path('/mnt/devbox-scratch/dev-user/ohm-combined-prs-20261028')
R = P / 'whole-wild-width-v2'
DEST = Path(sys.argv[1])
WILD = '0d6335808b647d499f3d74993b602e64ff0625206c809bf4913c487eea380cd5'
NAME = 'e2e-6a4ba41917b202dd'
sha = lambda b: hashlib.sha256(b).hexdigest()

def file_sha(p):
    with p.open('rb') as f:
        return hashlib.file_digest(f,'sha256').hexdigest()

def save(p, v):
    with p.open('x') as f:
        json.dump(v, f, sort_keys=True, indent=2); f.write('\n')

def rd(p, h=None):
    b=p.read_bytes()
    if h: assert sha(b)==h, p
    return json.loads(b)

def sealed(p):
    st=p.stat()
    return [file_sha(p),st.st_size,st.st_mode,st.st_dev,st.st_ino,st.st_mtime_ns,st.st_ctime_ns]

def tree(p):
    return {str(f.relative_to(p)): ('symlink:' + os.readlink(f) if f.is_symlink() else sealed(f) if f.is_file() else 'dir') for f in sorted(p.rglob('*'))}

def digest(v):return sha(json.dumps(v,sort_keys=True,separators=(',',':')).encode())

def main():
    assert socket.gethostname() == 'charlie-ohm-c5-check-1025' and os.sched_getaffinity(0)=={24,25,26,27}
    assert DEST.is_absolute() and DEST.parent==P.parent and DEST.name.startswith('ohm-ty-server-e2e-search-control-') and not DEST.exists()
    assert shutil.disk_usage(P).free > 16*2**30
    DEST.mkdir(mode=0o700)
    worker=P/'protocol-v3/ruff_worker.py';assert file_sha(worker)=='9c2e4138072679b8ffff20d417fffad8f6bcd3cba1b0dd15309e2d935cbc0813'
    sp=importlib.util.spec_from_file_location('frozen_workspace',worker);n=importlib.util.module_from_spec(sp);sp.loader.exec_module(n);n.source()
    state=R/'states/composed';phase=R/'commands/repeat-composed';catalog=rd(R/'targets'/NAME/'all-widths.json','cf759d32f165dd6819eec5b2e2522e1be5902a7c30e6d75d3949c2da0b221b01')
    target=n.can/catalog['target']; rec=target.with_suffix('.rlink'); physical_out=n.actual(str(target.parent),state)
    recipe,=[r for r in catalog['recipes'].values() if r['phase']=='repeat-composed']; rawrec=recipe['raw_input_file']; positives=rd(R/rawrec['file'],rawrec['sha256']);assert len(positives)==412
    jobs=rd(phase/'physical.json');job,=[j for j in jobs if j['kind']=='link-only' and str(rec) in j['argv']];argv=job['argv'];native,=[j for j in jobs if j['kind']=='wild' and j['target']==str(target)]
    assert job['exit']==native['exit']==0 and argv[-2:]==['-Z','link-only']; ld=Path(native['exe']);assert file_sha(ld)==WILD
    rawargv=native['argv']; named=[Path(a[2:]) for a in rawargv if a.startswith('-L')]; assert len(named)==13 and named[0].name=='raw-dylibs' and 'psm' in named[1].parts and 'zstd-sys' in named[2].parts
    psm_logical=named[1]; psm_physical=n.actual(str(psm_logical),state); assert not (psm_physical/'libgcc_s.so').exists()
    def real(p):
        p=Path(p);return state/p.relative_to(n.can) if p.is_relative_to(n.can) else p
    static={};missing=[]
    for k,v in positives.items():
        f=real(k)
        if not f.exists():missing.append(Path(k).name); continue
        assert file_sha(f)==v['sha256'] and f.stat().st_size==v['bytes'], k
        static[k]=[v['sha256'],v['bytes']]
    assert len(static)==410 and len(missing)==2 and 'symbols.o' in missing and any(x.endswith('.res')for x in missing),missing
    gcc_s,=[Path(k)for k in static if Path(k).name=='libgcc_s.so'];assert gcc_s.is_file() and not str(gcc_s).startswith(str(psm_logical))
    untouched={'out':tree(physical_out),'psm':tree(psm_physical),'linker':sealed(ld),'original-inlay':sealed(n.src/n.scope),'mounted-inlay':sealed(worker.parent/'ruff-edited-inlay-hints.rs'),'ron':sealed(real(next(k for k in static if '/libron-' in k and k.endswith('.rlib'))))}
    save(DEST/'donor-before.json',untouched)
    assert untouched['out'][rec.name][0]=='27b707b07b9844f86ddd13a222de08d9b9ee41de7c32e1e0f9f727b865047976'; expected_list=(phase/'e2e-list').read_bytes()
    cache=rd(physical_out/(NAME+'.rlink-cache.json')); manifest=cache.get('manifest',cache); assert len(manifest['objects'])==139
    out=DEST/'out'; psm=DEST/'psm'; temp=DEST/'tmp';temp.mkdir()
    for a,b in ((physical_out,out),(psm_physical,psm)):
        subprocess.run(['cp','-a','--reflink=never',a,b],check=True)
        assert all(not x.samefile(b/x.relative_to(a)) for x in a.rglob('*') if x.is_file() and not x.is_symlink())
    asm=DEST/'hook.S';obj=DEST/'hook.o';asm.write_text('.text\n.type frozen_shadow_hook,@function\nfrozen_shadow_hook:\n  mov $231,%eax\n  mov $83,%edi\n  syscall\n  ud2\n.section .preinit_array,"aw",@preinit_array\n.quad frozen_shadow_hook\n.section .note.GNU-stack,"",@progbits\n')
    subprocess.run(['as','--64',asm,'-o',obj],check=True)
    ns,env,_=n.invocation(state,'composed',True,DEST)
    for i,b in enumerate(ns):
        if b=='--bind' and Path(ns[i+1]).is_relative_to(state):ns[i]='--ro-bind'
    at=ns.index('--chdir');ns[at:at]=['--bind',str(out),str(target.parent),'--ro-bind',str(psm),str(psm_logical),'--bind',str(temp),str(n.can/'tmp')]
    assert not any(b=='--bind' and Path(ns[i+1]).is_relative_to(state) for i,b in enumerate(ns)); assert not any('MAKE' in k for k in env)
    shadow=psm/'libgcc_s.so'; public=[]; merged_hashes=set(recipe['bodies']); original_roster=digest(static)
    for label in ('original','earlier-object','invalid-earlier-file','restored'):
        d=DEST/label;d.mkdir()
        if label=='earlier-object':shadow.write_text(f'INPUT ( {obj} {gcc_s} )\n')
        if label=='invalid-earlier-file':shadow.write_text('INVALID_LINK_SCRIPT_FOR_E2E_NEGATIVE (\n')
        if label=='restored':shadow.unlink()
        cmd=[*ns,'strace','-f','-qq','-s','1048576','-e','trace=execve','-o',str(d/'exec'),*argv]
        run=subprocess.run(cmd,env=env,capture_output=True,timeout=180);(d/'stdout').write_bytes(run.stdout);(d/'stderr').write_bytes(run.stderr)
        lines=(d/'exec').read_bytes().splitlines();tool=ld.name.encode();auth=[line for line in lines if b'execve("' in line and b'wild-ld/'+tool+b'"' in line and re.search(br'= 0$',line)];assert len(auth)==1,(label,len(auth),run.stderr[-1000:]);assert not any(b'--threads=' in x for x in auth)
        row={'phase':label,'rustc_exit':run.returncode,'stderr_sha256':sha(run.stderr),'stock_wild_exec_count':len(auth),'stock_wild_exec_sha256':sha(auth[0]),'overall_trace_sha256':file_sha(d/'exec')}; exe=out/NAME
        if label=='invalid-earlier-file':
            assert run.returncode!=0 and b'libgcc_s.so' in run.stderr and b'INVALID_LINK_SCRIPT_FOR_E2E_NEGATIVE' in run.stderr,(label,run.stderr[-1600:]);row['diagnostic_mentions_shadow']=True
        else:
            assert run.returncode==0 and not run.stdout,(label,run.stderr[-2000:]); diagnostics=[json.loads(line) for line in run.stderr.splitlines()]; assert diagnostics==[{'$message_type':'artifact','artifact':str(target),'emit':'link'}],diagnostics; row['diagnostic_count']=0; row['artifact_events']=len(diagnostics); raw=file_sha(exe);row['elf_sha256']=raw;row['elf_bytes']=exe.stat().st_size
            assert (raw in merged_hashes)==(label!='earlier-object'),(label,raw)
            listing=subprocess.run([*ns,str(target),'--list'],env=env,capture_output=True,timeout=90);(d/'list').write_bytes(listing.stdout);(d/'list.stderr').write_bytes(listing.stderr)
            row['list_exit']=listing.returncode;row['list_sha256']=sha(listing.stdout);row['listed_tests']=listing.stdout.count(b': test\n');assert not listing.stderr
            if label=='earlier-object': assert listing.returncode==83 and not listing.stdout
            else: assert listing.returncode==0 and listing.stdout==expected_list
            subprocess.run(['cp','--reflink=auto',exe,d/'e2e'],check=True); assert file_sha(d/'e2e')==raw and not exe.samefile(d/'e2e')
        save(d/'digest.json',row);public.append(row)
    assert public[0]['elf_sha256']==public[-1]['elf_sha256']
    assert all(file_sha(real(k))==v[0] and real(k).stat().st_size==v[1]for k,v in static.items())
    finish={'out':tree(physical_out),'psm':tree(psm_physical),'linker':sealed(ld),'original-inlay':sealed(n.src/n.scope),'mounted-inlay':sealed(worker.parent/'ruff-edited-inlay-hints.rs'),'ron':sealed(real(next(k for k in static if '/libron-' in k and k.endswith('.rlib'))))};assert finish==untouched;save(DEST/'donor-after.json',finish);n.source()
    result={'source_role':'-17 scoped authentic ty_server e2e link-only replay, not a new full Cargo command','name':NAME,'cpus':sorted(os.sched_getaffinity(0)),'cargo_jobserver_forwarded':False,'product_worker_count_measured':False,'stock_wild':WILD,'source_ruff':rd(P/'ruff.json')['pin'],'native_inputs':len(positives),'still_available_positive_files':len(static),'still_available_positive_bytes':sum(r[1] for r in static.values()),'unchanged_positive_roster_sha256':original_roster,'prior_temp_files_not_read':['symbols.o','GCC plugin resolution file (empty in acquisition)'],'retained_native_default_sha256':recipe.get('bodies'),'whole_donor_before_after':digest(untouched),'previous_stock_rustc_exec_sha256':job['raw'],'previous_stock_wild_exec_sha256':native['raw'],'recipe_bytes':untouched['out'][rec.name][1],'recipe_sha256':untouched['out'][rec.name][0],'rust_object_count':len(manifest['objects']),'cache_executable_record_fields':sorted(manifest['executable']),'cache_file_sha256':file_sha(physical_out/(NAME+'.rlink-cache.json')),'previous_exe_sha256':untouched['out'][NAME][0],'previous_list_sha256':sha(expected_list),'hook_object':file_sha(obj),'phases':public};save(DEST/'result.json',result);print(json.dumps(result,sort_keys=True))

try: main()
except BaseException:
    if DEST.is_dir() and not (DEST/'result.json').exists() and not (DEST/'failure.txt').exists():(DEST/'failure.txt').write_text(traceback.format_exc())
    raise
