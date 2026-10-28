#!/usr/bin/env python3
import collections,csv,hashlib,json,os,re,signal,subprocess,sys
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
from common import *
from summarize import summarize

def need(cond,msg):
    if not cond:raise RuntimeError(msg)
def copy(a,b):
    need(not os.path.lexists(b),'occupied snapshot '+str(b))
    subprocess.run(['cp','-a','--reflink=auto',str(a),str(b)],check=True)
def sha_bytes(data):return hashlib.sha256(data).hexdigest()
def run_cohort(which,plan):
    cfg=plan['cohorts'][which];out=HERE/which;t=SLOTS/which
    out.mkdir();t.mkdir(mode=0o700);(t/'bin').mkdir();(t/'linker').mkdir()
    paths=dict(cargo=t/'cargo',wild=t/'wild',rustc=RUST/'rustc',linker_wrapper=t/'linker/ld.bfd')
    for path in [t/'bin/cc',t/'rustc-wrapper',paths['linker_wrapper']]:path.symlink_to(WRAP)
    env=dict(os.environ,CARGO_HOME=str(HOME_DIR),CARGO_TARGET_DIR=str(TARGET),RUSTC=str(paths['rustc']),RUSTDOC=str(RUST/'rustdoc'),CARGO_NET_OFFLINE='true',PATH=f"{t/'bin'}:{RUST}:{os.environ['PATH']}",CARGO_TERM_COLOR='never',SSL_CERT_DIR='/etc/ssl/certs',RUSTC_WRAPPER=str(t/'rustc-wrapper'),OHM_RELEASE_WILD_DIR=str(RUST.parent/'lib/rustlib/x86_64-unknown-linux-gnu/bin/wild-ld'),OHM_WRAPPED_WILD_DIR=str(t/'linker'),OHM_ACTUAL_WILD=str(paths['wild']),OHM_SINGLE_COUNTER=str(COUNTER))
    pristine=input_state();need(pristine==plan['pristine'],'retired fixture failed pristine validation')
    save(out/'before.json',pristine);original=EDIT.read_bytes();st=EDIT.stat()
    def put(i):
        buf=edit_bytes(original,cfg['letter'],i);dig=sha_bytes(buf)
        need(dig==cfg['edits_sha256'][str(i)] and len(buf)==cfg['source_bytes'],'edit differs from registration')
        EDIT.write_bytes(buf);return dig,EDIT.stat().st_mtime_ns
    def select(arm):
        for key,src in zip(('cargo','wild'),ARMS[arm]):
            n=paths[key].with_suffix('.next');os.link(src,n);os.replace(n,paths[key]);n.unlink(missing_ok=True);need(paths[key].samefile(src),'wrong selected binary')
    def run(mode,arm,label,kind):
        log=out/label;log.mkdir();select(arm);argv=[str(WRAP),'cargo',str(paths['cargo']),*CMD]
        if mode=='native' and kind=='admission':
            argv=['strace','-ff','-qq','-s','450','-e','trace=execve,execveat','-o',str(log/'exec'),*argv]
        with (log/'cargo.log').open('x') as f:
            rc=subprocess.run(argv,cwd=SRC,env=dict(env,OHM_ROLE_MODE=mode,OHM_ROLE_LOG=str(log)),stdout=f,stderr=subprocess.STDOUT).returncode
        body=(log/'cargo.log').read_text(errors='replace');need(rc==0 and re.search(r'^\s*Finished ',body,re.M),f'{label}: cargo rc {rc}: '+body[-1400:])
        need(not re.search(r'^\s*(?:Running|Downloading|Updating) |^running \d+ tests?',body,re.M),'unexpected test execution or network activity')
        rebuilt=sorted(re.findall(r'^\s*(Checking|Compiling) (.+)$',body,re.M))
        if kind=='warm':return rebuilt
        need(len(rebuilt)==1 and rebuilt[0][0]=='Compiling' and rebuilt[0][1].startswith('uv v'),f'{label}: unexpected package roster {rebuilt}')
        if kind=='structural':return rebuilt
        tests=sorted(re.findall(r'^\s*Executable (.+)$',body,re.M));need(len(tests)==72 and any(s.startswith('tests/it/') for s in tests),'wrong test manifest')
        records=[jread(p) for p in log.glob('*.json')]
        rr=collections.Counter(r['role'] for r in records);need(rr=={'cargo':1,'rustc':6,'wild':5},f'{label}: wrong role roster {rr}')
        if mode=='native':audit_native(log,paths,records)
        totals={r:sum(x.get('instructions',0) for x in records if x['role']==r) for r in ('cargo','rustc','wild')}
        for r in records:
            if mode=='count':need(r['instructions']>0 and r['instructions']==sum(r['threads'].values()),'incomplete PID/thread count')
        roster=dict(compiled=rebuilt,tests=tests,roles=sorted((r['role'],json.dumps(r['key'])) for r in records))
        files=artifacts(r['key'] for r in records if r['role']=='wild');need(len(files)==5,'missing output ELF')
        save(log/'receipt.json',dict(roster=roster,totals=totals,files=files,source_sha256=digest(EDIT),mtime_ns=EDIT.stat().st_mtime_ns,role_counts=rr))
        return roster,totals,files
    touched=False;parked_home=False;active_home=False
    try:
        copy(HOME_DIR,t/'home-clone');HOME_DIR.rename(t/'original-home');parked_home=True
        (t/'home-clone').rename(HOME_DIR);active_home=True
        copy(SEED,TARGET)
        run('native','base','warm','warm')
        need(not run('native','base','fresh','warm'),'original seed configuration failed to settle')
        touched=True;put(0);run('native','base','structural','structural')
        need(not run('native','base','structural-fresh','warm'),'structural edit failed to settle')
        TARGET.rename(t/'predecessor')
        for spec in cfg['admission_order']:copy(t/'predecessor',t/('slot-'+spec.replace('/','-')))
        expected=None
        for phase,jobs in [('admission',[(1,cfg['admission_order'])]),('samples',[(i,['count/'+('base' if c=='A' else 'candidate') for c in o]) for i,o in zip(cfg['edits'],cfg['orders'])])]:
            with (out/(phase+'.csv')).open('x',newline='') as stream:
                fields=['cohort','phase','pair_index','literal_id','position','arm','mode','source_sha256','mtime_ns','cargo','rustc','wild','total','receipt']
                wr=csv.DictWriter(stream,fields);wr.writeheader()
                for index,(i,cells) in enumerate(jobs):
                    dig,mt=put(i);ref_outputs=None
                    for pos,spec in enumerate(cells):
                        mode,arm=spec.split('/');slot=t/('slot-'+spec.replace('/','-'));label=f'{phase}-{index:02}-{pos}-{mode}-{arm}'
                        slot.rename(TARGET)
                        try:roster,counts,files=run(mode,arm,label,phase)
                        finally:TARGET.rename(slot)
                        if expected is None:expected=roster
                        need(roster==expected,f'{label}: exact workload roster mismatch')
                        normalized={k:(v['size'],v['canonical_sha256']) for k,v in files.items()}
                        if ref_outputs is None:ref_outputs=normalized
                        need(ref_outputs==normalized,f'{label}: unregistered artifact drift')
                        need(dig==digest(EDIT) and mt==EDIT.stat().st_mtime_ns,'source shifted within pair')
                        wr.writerow(dict(cohort=which,phase=phase,pair_index=index,literal_id=i,position=pos,arm=arm,mode=mode,source_sha256=dig,mtime_ns=mt,total=sum(counts.values()),receipt=label+'/receipt.json',**counts));stream.flush()
                    print(which,phase,index,'complete',flush=True)
            if phase=='admission':save(out/'admission.json',dict(roster=expected,role_counts={'cargo':1,'rustc':6,'wild':5},tests=len(expected['tests']),cells=cfg['admission_order'],same_source_sha256=cfg['edits_sha256']['1']))
    except BaseException as e:
        save(out/'rejected.json',{'error':str(e),'type':type(e).__name__});raise
    finally:
        if os.path.lexists(TARGET):TARGET.rename(t/'interrupted-target')
        if touched:
            EDIT.write_bytes(original);os.utime(EDIT,ns=(st.st_atime_ns,st.st_mtime_ns))
        if active_home:HOME_DIR.rename(t/'used-home')
        if parked_home:(t/'original-home').rename(HOME_DIR)
        for role in ('cargo','wild'):paths[role].unlink(missing_ok=True)
        restored=input_state();save(out/'restored.json',{'matches_registration':restored==pristine,'state':restored});need(restored==pristine,'retired fixture restoration failed')
    print(which,'restored',flush=True)

def main():
    p=jread(HERE/'plan.json');need((HERE/'registered.sha256').read_text().split()[0]==digest(HERE/'plan.json'),'registration changed')
    need(p['cpus']==sorted(os.sched_getaffinity(0)),'wrong affinity')
    for n,v in p['code_sha256'].items():need(digest(HERE/n)==v,'registered harness changed: '+n)
    for arm,(a,b) in ARMS.items():need({'cargo':digest(a),'wild':digest(b)}==p['arm_hashes'][arm],'arm changed')
    for x,k in [(RUST/'rustc','rustc_sha256'),(RUST/'rustdoc','rustdoc_sha256'),(COUNTER,'counter_sha256'),(WRAP,'wrapper_sha256')]:need(digest(x)==p[k],f'{x} changed')
    SLOTS.mkdir(mode=0o700)
    with (HERE/'calibration.log').open('x') as log:subprocess.run([sys.executable,'-B',str(W/'tree-count/calibrate.py'),str(HERE/'calibration')],stdout=log,stderr=subprocess.STDOUT,check=True)
    need((HERE/'calibration/PASS.json').is_file(),'calibration failed')
    for item in ('initial','replica'):run_cohort(item,p)
if __name__=='__main__':
    signal.signal(signal.SIGTERM,lambda a,b:(_ for _ in ()).throw(KeyboardInterrupt()))
    try:main()
    finally:
        if (HERE/'plan.json').is_file():summarize()
