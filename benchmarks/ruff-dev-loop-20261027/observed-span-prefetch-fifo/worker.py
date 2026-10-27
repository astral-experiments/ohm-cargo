"""Launch one clean native Ruff process in its frozen mount namespace and qualify all artifacts and readers."""
import argparse, ctypes, gzip, hashlib, os, re, shutil, subprocess, sys, time
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parent))
from common import CARGO_HOME, FROZEN, PIN, RUFF, SONAME, dump, env, git, load, need, sha, trace, diagnostics
from witness import OpenWatch, stamp, as_digest, audit_json, find_observers, read_proofs, trusted_ancestors, directory_inventory, rustc_open_calibration
H=Path(__file__).resolve().parent; plan=load(H/'ruff-prefetch-registration.json'); subjects=plan['subjects']
cli=argparse.ArgumentParser(description=__doc__);cli.add_argument('arm',choices=['V','C']);cli.add_argument('mode',choices=['build','test']);cli.add_argument('phase',choices=['prepare','anchor','timed','audit','final','train']);cli.add_argument('out',type=Path);cli.add_argument('helper',type=Path);cli.add_argument('--ref',type=Path);a=cli.parse_args();d=a.out;d.mkdir();ref=load(a.ref) if a.ref else None
assert not sys.flags.optimize
rustc=FROZEN/'bin/rustc';cargo=FROZEN/'bin/cargo';driver=FROZEN/'lib'/SONAME;config=env();timed=a.phase=='timed';traced=a.phase in ('anchor','audit','final','train','prepare');cwd=a.mode
need(sha(cargo)==subjects['cargo_'+('candidate' if a.arm=='C' else 'control')]['sha256'] and sha(rustc)==subjects['rustc_sha256'] and sha(driver)==subjects['compiler_driver_sha256'],'mounted subjects')
need(git('rev-parse','HEAD')==PIN and sorted(os.sched_getaffinity(0))==list(range(24)) and config['CARGO_BUILD_JOBS']=='8','Ruff or affinity mismatch')
command=['cargo','+ohm',a.mode]+(['--no-run'] if a.mode=='test' else [])+['--locked','--offline'];w=None
if ref:
    paths=ref['elf'];pf=ref['all_observers'];pre={p:stamp(p) for p in paths};proof=read_proofs(pf,a.helper)
    need(pre==ref['stamps'] and proof==ref['proofs'],('changed pre-run reference',d))
    if timed:
        watched=[rustc]
        for prefix in ('cc','gcc','clang','ld','ld.bfd','ld.lld','wild','mold','collect2'):
            p=shutil.which(prefix); 
            if p:watched.append(Path(p).resolve())
        cc=shutil.which('cc');c2=subprocess.run([cc,'-print-prog-name=collect2'],capture_output=True,text=True,check=True).stdout.strip() if cc else ''
        if c2 and Path(c2).is_file():watched.append(Path(c2).resolve())
        # Executable watchers are calibrated independently. Watch only compiler/linker images,
        # avoiding unrelated registry Cargo file reads; all target programs are examined in trace.
        w=OpenWatch(list(dict.fromkeys(watched)));need(not w.take(),'unexpected event before command')
if traced:command=['strace','-ff','-qq','-s','65536','-e','trace=execve,execveat,prctl','-o',str(d/'exec'),*command,'--message-format=json']
with (d/'stdout').open('wb') as sout,(d/'stderr').open('wb') as serr:
    start=time.monotonic_ns();proc=subprocess.run(command,cwd=RUFF,env=config,stdin=subprocess.DEVNULL,stdout=sout,stderr=serr);elapsed=time.monotonic_ns()-start
rec={'ns':elapsed,'mode':a.mode,'arm':a.arm,'phase':a.phase,'normal_terminal':timed,'status':proc.returncode,'argv':command,'cargo_sha256':sha(cargo)}
if w:
    rec['executable_open_events']=w.take();rec['watched_image_paths']=sorted(w.paths.values());w.close()
dump(d/'invocation.json',rec)
err=(d/'stderr').read_text();need(proc.returncode==0 and 'Blocking waiting' not in err,(proc.returncode,str(d),err[-1200:]));
if ref:
    post={p:stamp(p) for p in paths};post_proofs=read_proofs(pf,a.helper);need(pre==post==ref['stamps'] and proof==post_proofs==ref['proofs'],('modified shared ELFs/OBS1',d))
    rec.update(pre_stamp_sha256=as_digest(pre),post_stamp_sha256=as_digest(post),pre_proof_sha256=as_digest(proof),post_proof_sha256=as_digest(post_proofs))
if timed:
    status=[l.strip() for l in err.splitlines() if l.lstrip().startswith(('Compiling ','Checking ','Running ','Linking '))];need(not status and not rec['executable_open_events'],('native image open or status',d,status,rec['executable_open_events']));need(not (d/'stdout').read_bytes() and 'Finished' in err,('terminal output',d))
else:
    j=audit_json(d/'stdout',a.mode);t=trace(d);outimages=[p for _,p in t['executions']];need(any(Path(n).name=='cargo' and Path(n).is_file() and Path(n).samefile(cargo) for n in outimages),('did not execute selected Cargo',outimages[:6]));names=[]
    for p in d.glob('exec.*'):
        for line in p.read_text(errors='replace').splitlines():
            if 'prctl(PR_SET_NAME, "cargo-checksum"' in line and re.search(r'= 0$',line):names.append(p.name)
    rec.update(**{k:j[k] for k in ['units','dirty','executables','roster_sha256','message_sha256']},processes=t,checksum_worker_starts=names)
    if a.phase in ('anchor','audit','final'):
        need(not(j['dirty'] or t['rustc'] or t['rustc_queries'] or t['linkers'] or t['target_execs']),('non-fresh audit',d,j['dirty'],t))
    if ref:
        need(all(j[k]==ref[k] for k in ['elf','executables','roster_sha256','message_sha256']),('roster or messages changed',d))
    if a.phase in ('anchor','final'):
        nseen,allobs=find_observers(); active_ron=any('ron@0.12.0' in r and '"kind": ["lib"]' in r for r in j['roster'])
        # Cargo package IDs can use the compact crates.io URL `#ron@0.12.0` or otherwise spelled registry identities.
        need(active_ron==(a.mode=='test'),('Ron graph membership',a.mode,active_ron)); need(all(o['name']=='ron' for o in allobs),('unexpected source reader',allobs))
        if a.mode=='test':need(len(allobs)==1,('expected sole actual Ron',nseen,allobs))
        proofs=read_proofs(allobs,a.helper);root={**j,'all_observers':allobs,'proofs':proofs,'scanned_compiler_dep_info':nseen,'stamps':{p:stamp(p) for p in j['elf']},'raw_sha256':{p:sha(p) for p in j['elf']},'cargo_home_ancestors':trusted_ancestors(CARGO_HOME),'exec_open_calibration':rustc_open_calibration(rustc,config)}
        root['cache_inventory']={name:directory_inventory(CARGO_HOME/name) for name in ['.ohm-registry-json-v1','.ohm-git-index-sha1dc-v1']};need(root['cache_inventory']['.ohm-registry-json-v1']['files']>0 and all(p['trusted'] for p in root['cargo_home_ancestors']),('manifest cache inaccessible',root['cache_inventory'],root['cargo_home_ancestors']))
        # The candidate/control tree includes the v1 registry JSON cache and upstream Git verification. It does not contain #249's SHA1DC proof directory.
        (ruff,)=set(p for p in j['executables'] if Path(p).name=='ruff');root['diagnostics']=diagnostics(Path(ruff),False);dump(d/'anchor.json',root)
    if a.phase=='train':
        nseen,allobs=find_observers();rec['training_proof_state']=[{'name':o['name'],'encoded':o['encoded'],'has_footer':Path(o['encoded']).read_bytes()[-41:-37]==b'OBS1','complete':Path(o['encoded']).read_bytes()[-33:-32]==b'\x01'} for o in allobs]
dump(d/'receipt.json',rec)
