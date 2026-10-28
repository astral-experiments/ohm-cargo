"""Obtain the two ephemeral stock-linker operands with a native forwarding-only shim."""
from base64 import b64decode
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import socket
import subprocess
import sys
import traceback

P=Path('/mnt/devbox-scratch/dev-user/ohm-combined-prs-20261028');R=P/'whole-wild-width-v2'
D=Path('/mnt/devbox-scratch/dev-user/ohm-ty-server-e2e-native-capture-20261028-v1'); NAME='e2e-6a4ba41917b202dd'

def fhash(p):
    with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def rd(p):return json.loads(p.read_bytes())
def save(p,j):p.write_text(json.dumps(j,sort_keys=True,indent=2)+'\n')
def h(b):return hashlib.sha256(b).hexdigest()
def seal(f):
    s=f.stat();return [fhash(f),s.st_size,s.st_dev,s.st_ino,s.st_mode,s.st_mtime_ns,s.st_ctime_ns]
def run():
    assert os.sched_getaffinity(0)=={24,25,26,27} and socket.gethostname()=='charlie-ohm-c5-check-1025';assert not D.exists() and shutil.disk_usage(P).free>16*2**30;D.mkdir(mode=0o700)
    acquire=D/'acquired';acquire.mkdir(mode=0o700); tmp=D/'tmp';tmp.mkdir(); c=D/'capture.c';c.write_bytes(b64decode(C_SOURCE)); binary=D/'capture-shim';stock=R/'stock-wild';assert fhash(stock)=='0d6335808b647d499f3d74993b602e64ff0625206c809bf4913c487eea380cd5'
    subprocess.run(['cc','-O2',f'-DCAPTURE="{acquire}"',f'-DSTOCK="{stock}"',c,'-o',binary],check=True)
    sp=importlib.util.spec_from_file_location('frozen_workspace',P/'protocol-v3/ruff_worker.py');n=importlib.util.module_from_spec(sp);sp.loader.exec_module(n);n.source()
    state=R/'states/composed';phase=R/'commands/repeat-composed';catalog=rd(R/'targets'/NAME/'all-widths.json');target=n.can/catalog['target'];rec=target.with_suffix('.rlink');pdir=n.actual(str(target.parent),state);out=D/'out';subprocess.run(['cp','-a','--reflink=never',pdir,out],check=True);assert all(not f.samefile(out/f.relative_to(pdir)) for f in pdir.rglob('*')if f.is_file() and not f.is_symlink())
    recipe,=[r for r in catalog['recipes'].values() if r['phase']=='repeat-composed'];fr=recipe['raw_input_file'];positive=rd(R/fr['file']);assert fhash(R/fr['file'])==fr['sha256'];ar=recipe['raw_argv_file'];prior=rd(R/ar['file']);assert fhash(R/ar['file'])==ar['sha256']
    rows=rd(phase/'physical.json');job,=[x for x in rows if x['kind']=='link-only' and str(rec)in x['argv']];native,=[x for x in rows if x['kind']=='wild' and x['target']==str(target)];ld=Path(native['exe']);assert fhash(ld)==fhash(stock)
    def real(s):
        p=Path(s);return state/p.relative_to(n.can) if p.is_relative_to(n.can) else p
    keep={k:seal(real(k))for k in positive if real(k).exists()}; assert len(keep)==410 and all(v[0]==positive[k]['sha256']for k,v in keep.items()); guards={str(f):seal(f)for f in [pdir/rec.name,pdir/NAME,pdir/(NAME+'.rlink-cache.json'),ld,n.src/n.scope,n.k/'ruff-edited-inlay-hints.rs']}
    ns,env,_=n.invocation(state,'composed',True,D)
    for i,b in enumerate(ns):
        if b=='--bind' and Path(ns[i+1]).is_relative_to(state):ns[i]='--ro-bind'
    i=ns.index('--chdir');ns[i:i]=['--bind',str(out),str(target.parent),'--bind',str(tmp),str(n.can/'tmp'),'--ro-bind',str(binary),str(ld)]
    res=subprocess.run([*ns,'strace','-f','-qq','-s','1048576','-e','trace=execve','-o',D/'exec',*job['argv']],env=env,capture_output=True,timeout=160);(D/'stdout').write_bytes(res.stdout);(D/'stderr').write_bytes(res.stderr)
    assert res.returncode==0 and not res.stdout and [json.loads(l)for l in res.stderr.splitlines()]==[{'$message_type':'artifact','artifact':str(target),'emit':'link'}],res.stderr[-2000:]
    vec=lambda p:[os.fsdecode(s)for s in p.read_bytes().split(b'\0')[:-1]];args=vec(acquire/'argv.bin');envrows=vec(acquire/'env.bin');pwd=os.fsdecode((acquire/'cwd.bin').read_bytes());assert len(args)==len(prior)==446 and pwd==str(n.src)
    diff=[(a,b)for a,b in zip(prior,args)if a!=b];assert len(diff)==3
    def temp_name(a):
        if a.endswith('/symbols.o'):return 'symbols.o', a
        if a.startswith('-plugin-opt=-fresolution='):return 'resolution.res',a.split('=',2)[-1]
        if a.startswith('-L') and a.endswith('/raw-dylibs'):return 'raw-dylibs',a[2:]
        raise AssertionError(a)
    substitutions={};new_names={}
    for a,b in diff:
        oldname,old=temp_name(a);newname,new=temp_name(b);assert oldname==newname;substitutions[old]=new;new_names[newname]=new
    captured={name:seal(acquire/name)[:2]for name in new_names};assert captured['symbols.o'][0]==positive[next(k for k in positive if k.endswith('/symbols.o'))]['sha256'] and captured['resolution.res']==[h(b''),0]
    mode=(acquire/'raw-dylibs').read_text();assert mode in ['absent','empty-directory']
    package={'argv':args,'cwd':pwd,'private_raw_env':str(acquire/'env.bin'),'environment_keys':sorted(x.split('=',1)[0]for x in envrows),'stable_sources':{k:str(real(k))for k in keep},'transient_source_paths':new_names,'temporary_root':str(n.can/'tmp'),'canonical_output_directory':str(target.parent),'raw_dylibs_mode':mode,'native_source':str(ld),'stock_copy':str(stock),'prior_412_positive_input_record':str(R/fr['file']),'input_substitutions':substitutions,'previous_arg_path':str(R/ar['file']),'unmodified_starting_state':str(state),'each_readonly_shared_state_tree':list(['target','shared','cargo','home','tmp']),'original_runtime_canonical':str(n.can)};save(acquire/'replay.json',package);os.chmod(acquire/'replay.json',0o600)
    lines=(D/'exec').read_bytes().splitlines();actual=[l for l in lines if b'execve("'+str(stock).encode()+b'"' in l and l.endswith(b'= 0')];assert len(actual)==1
    assert all(seal(real(k))==v for k,v in keep.items()) and all(seal(Path(k))==v for k,v in guards.items());n.source(); assert fhash(out/NAME) in recipe['bodies']; listing=subprocess.run([*ns,str(target),'--list'],env=env,capture_output=True,check=True);assert listing.stdout==(phase/'e2e-list').read_bytes() and not listing.stderr
    binding={'stock':fhash(stock),'acquisition_shim':fhash(binary),'literal_argc':len(args),'original_raw_argv_json':ar['sha256'],'raw_argv':fhash(acquire/'argv.bin'),'environment_sha256':fhash(acquire/'env.bin'),'environment_count':len(envrows),'cwd_sha256':fhash(acquire/'cwd.bin'),'temporary_operands':captured,'raw_dylibs_mode':mode,'still_existing_positive_files':len(keep),'still_existing_positive_bytes':sum(v[1]for v in keep.values()),'original_per_file_receipt':fr['sha256'],'guarded_native_originals_sha256':h(json.dumps(guards,sort_keys=True).encode()),'raw_child_line_sha256':h(actual[0]),'native_trace':fhash(D/'exec'),'e2e_elf':fhash(out/NAME),'e2e_bytes':(out/NAME).stat().st_size,'listing':h(listing.stdout),'tests_listed':listing.stdout.count(b': test\n'),'replay_spec_sha256':fhash(acquire/'replay.json'),'cpu_mask':[24,25,26,27],'jobserver':False,'permissions':oct((acquire/'env.bin').stat().st_mode&0o777),'change_count_in_native_argv':len(diff),'physical_donor_unchanged':True};save(D/'public.json',binding);print(json.dumps(binding,sort_keys=True))
try:run()
except BaseException:
    if D.is_dir():(D/'failure.txt').write_text(traceback.format_exc())
    raise
