"""Resume the same registered commands after exact independent stock byte authentication; reuse every existing invocation."""
from pathlib import Path
import csv,fcntl,hashlib,importlib.util,json,os,subprocess,sys
sys.path.insert(0,str(Path(__file__).resolve().parent))
from shared import *
def mod(name,file):
    spec=importlib.util.spec_from_file_location(name,HERE/file);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
old=mod('original_score','replay-screen.py');sup=mod('stock_supplement','replay-validate-new.py')
ORIGINAL='69055ed7558ef06c5fdb6892703e71b92422ccc32144797bbe2214f7722a2928'
SUPP='07aed068b84ac658559961f0b5b80a65ab0b1211d710ba640dc6a58cdbfcf62a'
def observed_expected(ed,rev):
    """Admit only a same-source, same-normalized ELF physically written by a single stock full rustc + bundled Wild."""
    original=load(old.ROOT/'expected.json');fields=load(P/'results'/ed/'Stock11'/'complete.json')['edit-again' if rev=='edited' else 'restore']['elfs']
    for file in sorted(sup.SAVED.glob('*/certificate.json')):
        v=load(file)
        if v['ed']!=ed or v['rev']!=rev:continue
        path=v['path'];prev=fields[path];need(v['masked']==prev['content_with_two_wild_fields_masked'] and file.parent==sup.wp(ed,rev,path),'independent source/ELF binding')
        for digest,rel in v['stock_full'].items():
            ref=P/'results'/rel;need(ref.is_relative_to(file.parent) and ref.name=='observation.json' and ref.parent.name in [f'force-{i}' for i in range(1,9)],'concrete stock observation')
            x=load(ref);need(x['state']==rev and x['ed']==ed and x['path']==path and x['elf']['raw']==digest and x['elf']['content_with_two_wild_fields_masked']==v['masked'] and x['elf']['size']==prev['size'],'stock product contract')
            need(len(x['stock_full_rustc'])==1 and x['stock_full_rustc'][0][2]=='full' and len(x['stock_wild'])==1 and x['stock_wild'][0][1:]==[Path(path).name,True,False],'full physical stock ELF')
            if digest not in original[ed][rev]['elfs'][path]:original[ed][rev]['elfs'][path].append(digest)
    return original
def check(ed,arm,kind,label,rev):
    keys=observed_expected(ed,rev);default=old.load;old.load=lambda path:keys if path==old.ROOT/'expected.json' else default(path)
    try:old.audit(ed,arm,kind,label,rev)
    except RuntimeError as e:
        if len(e.args)==1 and isinstance(e.args[0],tuple) and e.args[0][0]=='unverified ELF. Withhold this cohort':sys.exit(77)
        raise
def actual_inv(ed,arm,kind,label,rev):
    d=old.where(ed,arm,kind,label);f=d/'invocation.json'
    if not f.exists():subprocess.run([*shell(ed,old.NAME[arm]),sys.executable,'-B',str(HERE/'replay-screen.py'),'run',ed,arm,kind,label,rev],env=env(),check=True)
    v=load(f);need(v['source']==rev and v['kind']==kind and v['label']==label and v['traced']==(kind in ('pre','post')) and v['exit']==0 and v['command']==old.registered()['commands'] and v['binary']['cargo']==old.registered()['subjects'][arm]['pgo'],'wrong or incomplete earlier command')
    return v
def qa(ed,arm,kind,label,rev):
    d=old.where(ed,arm,kind,label)
    if (d/'verified.json').is_file():return
    rejected=d/'unexpected.json'
    if rejected.is_file() and load(rejected):
        first=d/('unrecognized-'+sha(rejected)+'.json')
        if not first.exists():shutil.copy2(rejected,first)
    cmd=[*shell(ed,old.NAME[arm]),sys.executable,'-B',__file__,'audit',ed,arm,kind,label,rev]
    r=subprocess.run(cmd,env=env())
    if r.returncode==77:
        findings=d/'unexpected.json';need(bool(load(findings)),'absent unrecognized raw');s=d/('unrecognized-'+sha(findings)+'.json')
        if not s.exists():shutil.copy2(findings,s)
        sup.from_gate(d)
        subprocess.run(cmd,env=env(),check=True)
    else:need(r.returncode==0,('verification failure',d,r.returncode))
    need((d/'verified.json').is_file(),'verified byte and semantic outcome')
def prefix(kind,ed,steps):
    for label,edited in steps:
        rev='edited' if edited else 'original'
        for a in 'AC':
            d=old.where(ed,a,kind,label)
            if not (d/'verified.json').is_file():
                mark(state(ed,old.NAME[a]),fixture(ed),edited);actual_inv(ed,a,kind,label,rev);qa(ed,a,kind,label,rev)
            else:actual_inv(ed,a,kind,label,rev)
def run():
    with (P/'bench.lock').open('a') as l:
        fcntl.flock(l,fcntl.LOCK_EX|fcntl.LOCK_NB);need(sha(HERE/'replay-screen.py')==ORIGINAL and sha(HERE/'replay-validate-new.py')==SUPP,'bound measurement and stock verification programs')
        grant=load(P/'results/A11-screen-resume');need(grant['plan']==old.REG and grant['runner']==ORIGINAL and grant['state_runner']==sha(__file__) and grant['stock_recertifier']==SUPP,'unbound continuation')
        need(sha(old.ROOT/'expected.json')==grant['first_gate_expected_sha256'] and (old.ROOT/'wasm-only/pair-08.json').is_file() and (P/'results/a11-registered-score.rc').read_text().strip()=='1','initial frozen gate not retained')
        need(not (old.ROOT/'complete.json').is_file(),'past completion')
        completed=old.ROOT/'wasm-only';assert all((completed/f'pair-{i:02}.json').is_file() for i in range(1,9))
        rows={k:[] for k in ('dirty','fresh')}
        for ed in old.registered()['endpoint_order']:
            prefix('pre',ed,[('starting-original',False),('starting-original-fresh',False)])
            for z in old.registered()['schedule'][ed]:
                n=z['pair'];edited=n%2==1;rev='edited' if edited else 'original';label=f'pair-{n:02}';pair=old.ROOT/ed/(label+'.json')
                if pair.is_file():
                    need(all((old.where(ed,a,k,label)/'verified.json').is_file() for a in 'AC' for k in rows),'completed pair missing independent verification')
                else:
                    for a in 'AC':mark(state(ed,old.NAME[a]),fixture(ed),edited)
                for kind in ('dirty','fresh'):
                    for slot,arm in enumerate(z['order'],1):
                        v=actual_inv(ed,arm,kind,label,rev);rows[kind].append({'endpoint':ed,'direction':z['direction'],'pair':n,'slot':slot,'arm':arm,'elapsed_ns':v['elapsed_ns']})
                if not pair.is_file():
                    for kind in ('dirty','fresh'):
                        for a in z['order']:qa(ed,a,kind,label,rev)
                    dump(pair,{'complete':True,'free_bytes':floors(),'loadavg':os.getloadavg()});print(ed,label,'verified',flush=True)
            prefix('post',ed,[('final-edited',True),('final-edited-fresh',True),('final-original',False),('final-original-fresh',False)])
        for k,v in rows.items():old.export_rows(k,v)
        dump(old.ROOT/'host-after.json',old.env_summary());dump(old.ROOT/'complete.json',{'plan':old.REG,'runner':ORIGINAL,'continuation':sha(__file__),'stock_verification':SUPP,'dirty_csv':sha(old.ROOT/'dirty.csv'),'fresh_csv':sha(old.ROOT/'fresh.csv'),'commands_timed':64})
if __name__=='__main__':
    if sys.argv[1:2]==['audit']:check(*sys.argv[2:]);sys.exit()
    run()
