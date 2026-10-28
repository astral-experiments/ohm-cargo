"""Recheck a previous empty link selection on the unchanged real formatter bin harness."""
from pathlib import Path
import collections,hashlib,json,os,runpy,shutil,subprocess
HERE=Path(__file__).resolve().parent
base=(HERE/'replay-v2.py').read_text()
exec(compile(base.split('guard();installed()')[0],str(HERE/'replay-v2.py'),'exec'))
guard();installed()
exec(compile(base[base.index('common_env='):base.index('historical=')],__file__,'exec'))
assert (HERE/'shadow-v2/complete.json').is_file();common_env.pop('WILD_WRITE_LAYOUT');q=HERE/'shadow-default';q.mkdir();diag=A['PLAN']['path']
src=q/'source.rs';shutil.copy2(HERE/'provider/diagnostics.rs',src)
assert sha(src)==A['PLAN']['file_sha256']['original']
n=J(D/'receipts/restore/native.json');old,=[x for x in n['links'] if token in x['output']]
wild=Path(old['exe']);dirs=[Path(s[2:]) for s in old['argv'] if s.startswith('-L')]
native,=[x for x in dirs if 'psm' in x.parts];real=STATE/native.relative_to(D)
shadow=q/'higher-priority';shutil.copytree(real,shadow)
assert not (real/'libgcc_s.so').exists() and not (shadow/'libgcc_s.so').exists()
libgcc=Path('/lib/x86_64-linux-gnu/libgcc_s.so.1').resolve();assert libgcc.is_file()
asm=q/'provider.s';asm.write_text('.text\n.globl write\n.type write,@function\nwrite:\n  mov $83,%edi\n  mov $231,%eax\n  syscall\n  ud2\n.size write, .-write\n.section .note.GNU-stack,"",@progbits\n')
obj=q/'force.o';subprocess.run(['/usr/bin/cc','-c','-x','assembler','-fPIC',str(asm),'-o',str(obj)],check=True)
(shadow/'libgcc_s.so').write_text(f'INPUT ( {obj} {libgcc} )\n')
samecmd=['cargo','+ohm','test','--no-run','-p','ruff_python_formatter','--locked','--offline','-j4','--message-format=json']
def run(call,phase,prefix,required=None):
    with (phase/(prefix+'.out')).open('xb') as so,(phase/(prefix+'.err')).open('xb') as se:r=subprocess.run([*ns,*call],env=common_env,stdout=so,stderr=se)
    if required is not None:assert r.returncode==required,(prefix,r.returncode,(phase/(prefix+'.err')).read_bytes()[-1500:])
    return r.returncode
helper=runpy.run_path(str(HERE/'linked-layout.py'))
for name,source,extra in [('original','original',False),('edited-shadow','reverse',True),('restored','original',False)]:
    d=q/name;d.mkdir();(d/'trace').mkdir()
    new=(C/(source+'.rs')).read_bytes()
    if src.read_bytes()!=new:src.write_bytes(new)
    ns=[*rootbind,'--ro-bind',str(src),str(SOURCE/diag)]
    if extra:ns+=['--ro-bind',str(shadow),str(native)]
    ns+=['--chdir',str(SOURCE),'--']
    run(['strace','-ff','-q','-s','1048576','-e','trace=execve,openat,openat2,clone,clone3,fork,vfork','-o',str(d/'trace/exec'),*samecmd],d,'cargo',0)
    rows=[json.loads(s) for s in (d/'cargo.out').read_bytes().splitlines()];assert rows[-1]=={'reason':'build-finished','success':True}
    rows=[r for r in rows if r['reason']=='compiler-artifact'];assert len(rows)==218
    f,=[Path(r['executable']) for r in rows if r['target']['kind']==['bin'] and r['profile']['test']]
    ar=A['native'](d/'trace',SDK);put(d/'processes.json',ar)
    ld=[l for l in ar['links'] if l['output']==str(f)];job=[j for j in ar['jobs'] if any(token in x for x in j['argv'])]
    assert len(ld)==len(job)==(0 if name=='original' else 1)
    cp=run([str(f),'--list'],d,'run')
    elf=STATE/f.relative_to(D);rli=next(elf.parent.glob('*.rlink'))
    dat={'source':source,'additional_native_input':extra,'native_library':str(native/'libgcc_s.so'),'real_sys_library':sha(libgcc),'obj':sha(obj),'script':sha(shadow/'libgcc_s.so'),'wild':sha(wild),'argv':samecmd,'units':len(rows),'fresh':sum(r['fresh'] for r in rows),'rustc':collections.Counter(j['kind'] for j in ar['jobs']),'wilds':len(ar['links']),'harness_job':job[0]['kind'] if job else 'fresh','config':sha(src),'rlink':sha(rli),'obj_inputs':{o.name:sha(o) for o in next(elf.parent.glob('*.rlink-objects')).glob('*.o')},'elf':sha(elf),'run_status':cp,'stdout':(d/'run.out').read_text()}
    if ld:
        rec=ld[0];t=(d/'trace'/('exec.'+str(rec['pid']))).read_text()
        # The genuine packaged Wild is the process opening the new path and explicit script inputs.
        import re
        dat['wild_argv']=rec['raw']; relatives={rec['pid']};todo=[rec['pid']];seen=set();hits=[]
        while todo:
            pid=todo.pop();seen.add(pid)
            t=(d/'trace'/('exec.'+str(pid))).read_text()
            for line in t.splitlines():
                if line.startswith(('clone(','clone3(','fork(','vfork(')):
                    child=re.search(r'= (\d+)$',line)
                    if child:
                        child=int(child.group(1));relatives.add(child)
                        if child not in seen:todo.append(child)
                if line.startswith(('openat(','openat2(')) and (str(native/'libgcc_s.so') in line or str(obj) in line or str(libgcc) in line):
                    hits.append([pid,line])
        dat['wild_family']=sorted(relatives);dat['actual_open']=hits
        assert dat['harness_job']=='link-only'
    dat['layout_request']=False
    put(d/'row.json',dat);print(name,dat['rustc'],dat['harness_job'],dat.get('selected_formatter_members'),cp,dat.get('selected_probe_object'),dat['elf'][:12],repr(dat['stdout']),flush=True)
items=[J(q/t/'row.json') for t in ('original','edited-shadow','restored')]
assert len({d['rlink'] for d in items})==1 and items[0]['obj_inputs']==items[1]['obj_inputs']==items[2]['obj_inputs']
assert [d['run_status'] for d in items]==[0,83,0] and items[0]['elf']==items[2]['elf']!=items[1]['elf']
assert all(any(v in line and re.search(r'= [0-9]+$',line) for _,line in items[1]['actual_open']) for v in (str(native/'libgcc_s.so'),str(obj)))
put(q/'complete.json',{'pass':True,'exact_same_original_restored':True,'consumer_original_rlink_unchanged':True})
