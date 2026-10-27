"""Authenticate an unrecognized raw ELF using independent same-source full stock builds; never inspect scored durations."""
from pathlib import Path
import fcntl,hashlib,json,os,signal,subprocess,sys,time
sys.path.insert(0,str(Path(__file__).resolve().parent))
from shared import *
from elf import elf
from replay_processes import parsed
from roster import audit_json
SCREEN=P/'results/a11-screen-v1';SAVED=P/'results/a11-screen-independent-stock';REF='StockProbe'
def atomic(p,data):
    f=p.with_suffix(p.suffix+'.tmp');f.write_text(json.dumps(data,indent=2,sort_keys=True)+'\n');os.replace(f,p)
def values(p):
    w=elf(p);return {k:w[k] for k in ['raw','content_with_two_wild_fields_masked','rodata_entsize','gnu_build_id','size']}
def wp(ed,rev,path):
    return SAVED/hashlib.sha256(json.dumps([ed,rev,path],separators=(',',':')).encode()).hexdigest()
def stock_run(ed,rev,path,width,case,root):
    d=root/(case+'-'+str(width));d.mkdir();view(ed,rev=='edited');trusted()
    live=TARGET/path;need(live.is_relative_to(TARGET) and not live.is_symlink() and live.is_file(),'private stock ELF');pdir=live.parent.parent/'fingerprint'
    need(sha(FROZEN/'bin/cargo')=='dd5cab154b8dcd09ccc2753160d314cade80979b2d055ee66aa9e2217e05e7e1','official stock Cargo')
    if case=='force':
        fps=[p for p in pdir.iterdir() if p.is_file() and not p.is_symlink() and p.suffix=='' and not p.name.startswith(('dep-','output-','ohm-','invoked.timestamp'))]
        need(len(fps)==1 and fps[0].stat().st_nlink==1,('normal per-unit Cargo fingerprint',pdir,[p.name for p in fps]))
        shutil.copy2(fps[0],d/'withheld');need(sha(fps[0])==sha(d/'withheld'),'private fingerprint witness');fps[0].unlink()
    rd,wr=os.pipe();os.write(wr,b'+'*(width-1));e=env()
    if case=='force':e['MAKEFLAGS']=f'-j --jobserver-auth={rd},{wr}'
    cmd=['strace','-ff','-qq','-s','262144','-e','trace=execve,execveat','-o',str(d/'exec'),*plan()['command']]
    try:
        with (d/'stdout').open('wb') as so,(d/'stderr').open('wb') as se:
            p=subprocess.Popen(cmd,cwd=WT,env=e,stdin=subprocess.DEVNULL,stdout=so,stderr=se,pass_fds=(rd,wr) if case=='force' else (),start_new_session=True)
            while p.poll() is None:
                if case=='force' and sum(l.lstrip().startswith('Compiling ') for l in (d/'stderr').read_text(errors='replace').splitlines())>1:
                    os.killpg(p.pid,signal.SIGTERM);p.wait();raise RuntimeError('unexpected units rebuilt')
                time.sleep(.2)
    finally:os.close(rd);os.close(wr)
    need(p.returncode==0,('stock full failed',d,(d/'stderr').read_text()[-400:]));j=audit_json(d/'stdout','test');r=parsed(d,j)
    if case=='force':need(len(r['rustc'])==1 and r['rustc'][0][2]=='full' and len(r['native_links'])==1 and r['native_links'][0][1:]==[live.name,True,False],('stock full + default real Wild only',r))
    if case=='fresh':need(not j['dirty'] and not r['rustc'] and not r['native_links'],'stock witness must remain fresh')
    atomic(d/'observation.json',{'ed':ed,'state':rev,'path':path,'offered_jobserver_workers':width,'roster':j['roster_sha256'],'stock_full_rustc':r['rustc'],'stock_wild':r['native_links'],'elf':values(live)})
def from_gate(where):
    gate=Path(where);ed,arm,stage=gate.relative_to(SCREEN).parts;need(arm in ('A','C') and ed in ('parser','wasm-only'),'illegal gate');rev=load(gate/'invocation.json')['source'];need(rev in ('edited','original'),'source')
    unknown=load(gate/'unexpected.json');need(unknown,'there are no unrecognized products');prior=P/'results'/ed/'Stock11'/'complete.json'
    phase='edit-again' if rev=='edited' else 'restore';known=load(prior)[phase]['elfs'];old=load(SCREEN/'expected.json')[ed][rev]['elfs']
    for name,new in sorted(unknown.items()):
        need(name in known and name in old and not Path(name).is_absolute(),'registered ELF path only')
        live=state(ed,'A11' if arm=='C' else 'Stock11')/'target'/name
        current=values(live);base=known[name]
        need(current['raw']==new and current['size']==base['size'] and current['content_with_two_wild_fields_masked']==base['content_with_two_wild_fields_masked'],('true outside-class/native product difference; stop',ed,rev,name,current,base))
        dst=wp(ed,rev,name);dst.mkdir(parents=True,exist_ok=True)
        required={base['raw'],new}
        other=SCREEN/ed/('C' if arm=='A' else 'A')/stage
        if (other/'verified.json').is_file() and (maybe:=load(other/'verified.json').get('elfs')):required.add(maybe[name])
        expected=base['content_with_two_wild_fields_masked']
        if (dst/'certificate.json').is_file():
            v=load(dst/'certificate.json');need(v['ed']==ed and v['rev']==rev and v['path']==name and v['masked']==expected,'bad existing native witness')
            if required<=set(v['stock_full']):continue
        st=state(ed,REF);mark(st,fixture(ed),rev=='edited')
        def invoke(case,width):
            dest=dst/(case+'-'+str(width));
            if (dest/'observation.json').is_file():return load(dest/'observation.json')
            subprocess.run([*shell(ed,REF),sys.executable,'-B',__file__,'inside',ed,rev,name,str(width),case,str(dst)],check=True,env=env())
            return load(dest/'observation.json')
        # If supplemental hypotheses from several source states occur, settle even when an older
        # saved receipt exists. Only a forced observation freshly made in its named state is used.
        if (st/'last-validated-native-state').is_file() and (st/'last-validated-native-state').read_text()!=rev and (dst/'settle-8/observation.json').is_file():
            raise RuntimeError('native stock state was shared with a different supplemental observation; new isolated witness required')
        invoke('settle',8);(st/'last-validated-native-state').write_text(rev)
        full={}
        for width in [1,8,2,3,4,5,6,7]:
            obs=invoke('force',width);need(obs['ed']==ed and obs['state']==rev and obs['path']==name and obs['elf']['content_with_two_wild_fields_masked']==expected,('non-matching stock output',obs))
            full[obs['elf']['raw']]=str((dst/('force-'+str(width))/'observation.json').relative_to(P/'results'))
            if required<=set(full):break
        need(required<=set(full),('stock could not independently reproduce exact ELF bytes',ed,rev,name,required,sorted(full)))
        invoke('fresh',8)
        atomic(dst/'certificate.json',{'ed':ed,'rev':rev,'path':name,'masked':expected,'stock_full':full,'gate':str(gate.relative_to(SCREEN)),'candidate_or_stock_checked':current})
        print('Verified exact stock variants',ed,rev,Path(name).name,len(full),flush=True)
if __name__=='__main__':
    if sys.argv[1:2]==['inside']:stock_run(sys.argv[2],sys.argv[3],sys.argv[4],int(sys.argv[5]),sys.argv[6],Path(sys.argv[7]));sys.exit()
    with (P/'bench.lock').open('a') as l:
        fcntl.flock(l,fcntl.LOCK_EX|fcntl.LOCK_NB);from_gate(sys.argv[1])
