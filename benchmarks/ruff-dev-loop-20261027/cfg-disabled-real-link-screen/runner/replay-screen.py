"""Untraced, balanced ordinary cargo command screen with separate untimed phase/oracle checks."""
import collections,csv,fcntl,os,subprocess,sys,time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
from shared import *
from inspect_products import cli,library
from replay_processes import parsed
from roster import audit_json
NAME={'A':'Stock11','C':'A11'}
REG='6dfd1b505f0ef72e101cea247d5bb669bec3f1eb6ef8058c685caabca9e38841'
ROOT=P/'results/a11-screen-v1'
def registered():
    f=TRANSFER/'A11-screen-plan.json';need(sha(f)==REG,'registered A11 plan');return load(f)
def images(arm):
    spec=registered();v={k:sha(p) for k,p in [('cargo',FROZEN/'bin/cargo'),('rustc',FROZEN/'lib'/SONAME),('frontend',FROZEN/'bin/rustc'),('wild',P/load(TRANSFER/'installation.json')['bundled_wild'])]}
    need(v=={'cargo':spec['subjects'][arm]['pgo'],'rustc':spec['rustc_driver_sha256'],'frontend':spec['rustc_frontend_sha256'],'wild':spec['wild_sha256']},v)
    return v
def where(ed,arm,kind,label):return ROOT/ed/arm/(kind+'-'+label)
def run(ed,arm,kind,label,rev):
    d=where(ed,arm,kind,label);d.mkdir(parents=True,exist_ok=False);spec=registered();edited=rev=='edited'
    view(ed,edited);trusted();floors();need(sorted(os.sched_getaffinity(0))==list(range(24)),'incorrect CPU set')
    binary=images(arm)
    trace=kind in ('pre','post');command=spec['commands'];prefix=['strace','-ff','-qq','-s','262144','-e','trace=execve,execveat','-o',str(d/'exec')] if trace else []
    with (d/'stdout').open('wb') as so,(d/'stderr').open('wb') as se:
        start=time.monotonic_ns();p=subprocess.run(prefix+command,cwd=WT,env=env(),stdin=subprocess.DEVNULL,stdout=so,stderr=se);elapsed=time.monotonic_ns()-start
    need(p.returncode==0 and 'Blocking waiting' not in (d/'stderr').read_text(),('ordinary cargo failed or blocked',d,p.returncode,(d/'stderr').read_text()[-750:]))
    dump(d/'invocation.json',{'binary':binary,'source':rev,'kind':kind,'label':label,'command':command,'exit':p.returncode,'traced':trace,'elapsed_ns':elapsed})
def audit(ed,arm,kind,label,rev):
    d=where(ed,arm,kind,label);r=load(d/'invocation.json');keys=load(ROOT/'expected.json')[ed][rev];edited=rev=='edited';j=audit_json(d/'stdout','test')
    need(j['roster_sha256']==keys['roster'] and j['message_sha256']==keys['messages'],('observably different roster/diagnostics',ed,arm,kind,label))
    fresh=kind=='fresh' or label.endswith('fresh');need(j['dirty']==([] if fresh else keys['dirty']),('unexpected dirty artifacts',ed,arm,kind,label,j['dirty']))
    rows=[json.loads(t) for t in (d/'stdout').read_bytes().splitlines() if t]
    out={'roster':j['roster_sha256'],'messages':j['message_sha256'],'dirty':j['dirty'],'units':j['units'],'executables':len(j['executables']),'elf_count':len(j['elf'])}
    if not fresh:
        prod={str(Path(f).relative_to(TARGET)):sha(f) for f in j['elf']};out['elfs']=prod
        unexpected={p:h for p,h in prod.items() if h not in keys['elfs'][p]};dump(d/'unexpected.json',unexpected);need(not unexpected,('unverified ELF. Withhold this cohort',ed,arm,kind,label,unexpected))
        arts=[v for v in rows if v['reason']=='compiler-artifact'];ruff,={a['executable'] for a in arts if a['target']['kind']==['bin'] and a['target']['name']=='ruff' and not a['profile']['test'] and a['executable']}
        out['cli']=cli(ruff,ed,edited);out['caller']=library(rows,ed=='wasm-only' and edited,d);out['listing']={}
        for a in arts:
            if a['target']['kind']==['test'] and a['target']['name']=='api':
                txt=subprocess.check_output([a['executable'],'--list'],text=True,env=env());need(txt.strip()=='0 tests, 0 benchmarks','native test list');out['listing'][Path(a['manifest_path']).parent.name]=txt.strip()
        need(len(out['listing'])==2,'both test outputs')
    if r['traced']:
        tr=parsed(d,j);actual=collections.Counter(map(tuple,[x[1:] for x in tr['rustc']]));expected=collections.Counter(map(tuple,keys['phase_jobs'][arm]));wild=sorted([x[1:] for x in tr['native_links']])
        need(actual==(collections.Counter() if fresh else expected) and wild==([] if fresh else keys['wild']) and not tr['native_probes'],('real before/after phase or link changed',ed,arm,kind,label,actual,expected))
        out['phase_trace']=tr
    dump(d/'verified.json',out)
def expected():
    ex={}
    for ed in registered()['endpoint_order']:
        root=P/'results'/ed;materials={arm:load(root/NAME[arm]/'complete.json') for arm in NAME};witness=load(root/'StockProbe'/'complete.json');ex[ed]={}
        for rev,pname in [('edited','edit-again'),('original','restore')]:
            a=materials['A'][pname];c=materials['C'][pname]
            need(all(a[k]==c[k] for k in ('roster','messages','dirty','cli','caller','units','executables','elf_count')),'preflight observations differ')
            mode=sorted([x[3] for x in c['rustc'] if x[1]=='api' and x[2]=='link-only']);need([v+':api' for v in mode]==sorted(registered()['edits'][ed]['expected_cached_jobs']),'actual native cached jobs')
            need(sorted(x[1:] for x in a['wild'])==sorted(x[1:] for x in c['wild']),'inconsistent native jobs')
            rec={k:a[k] for k in ('roster','messages','dirty')};rec['phase_jobs']={arm:[x[1:] for x in subj[pname]['rustc']] for arm,subj in materials.items()};rec['wild']=sorted(x[1:] for x in a['wild']);rec['elfs']={}
            for k,sa in a['elfs'].items():
                sc=c['elfs'][k];need(sa['content_with_two_wild_fields_masked']==sc['content_with_two_wild_fields_masked'],('different ELF payload',ed,pname,k))
                allowed={sa['raw'],sc['raw']}
                if rev=='edited':
                    aa=materials['A']['edit']['elfs'][k];cc=materials['C']['edit']['elfs'][k]
                    need(aa['content_with_two_wild_fields_masked']==cc['content_with_two_wild_fields_masked']==sa['content_with_two_wild_fields_masked'],'first-dirty output changed outside known classes')
                    allowed |= {aa['raw'],cc['raw']}
                if len(allowed)>1:
                    actual=witness['phases'][pname][k];need(allowed==set(actual['required_raw']) and allowed<=set(actual['forced_full_jobs_1_8']+[actual['independent_cold_full_original']]),('stock variants missing',k,allowed,actual))
                rec['elfs'][k]=sorted(allowed)
            ex[ed][rev]=rec
    return ex
def exec_host(fn,ed,arm,*args):
    subprocess.run([*shell(ed,NAME[arm]),sys.executable,'-B',__file__,fn,ed,arm,*args],check=True,env=env())
def prepost(kind,ed,labels):
    for label,edits in labels:
        for arm in 'AC':
            mark(state(ed,NAME[arm]),fixture(ed),edits);rev='edited' if edits else 'original';exec_host('run',ed,arm,kind,label,rev);exec_host('audit',ed,arm,kind,label,rev)
def export_rows(kind,results):
    with (ROOT/(kind+'.csv')).open('x',newline='') as f:
        d=csv.DictWriter(f,fieldnames=['endpoint','direction','pair','slot','arm','elapsed_ns']);d.writeheader();d.writerows(results)
def env_summary():
    return {'host':socket.gethostname(),'uname':list(os.uname()),'processor_count':os.cpu_count(),'mount':subprocess.check_output(['findmnt','-n','-o','FSTYPE,MAJ:MIN','-T',P],text=True).strip(),'loadavg':os.getloadavg(),'pressure':Path('/proc/pressure/cpu').read_text().splitlines(),'available_bytes':floors()}
if __name__=='__main__':
    if sys.argv[1:2]==['run']:run(*sys.argv[2:]);sys.exit()
    if sys.argv[1:2]==['audit']:audit(*sys.argv[2:]);sys.exit()
    if sys.argv[1:2]==['check']:v=expected();print([(ed,[(rev,len(x['elfs'])) for rev,x in states.items()]) for ed,states in v.items()]);sys.exit()
    with (P/'bench.lock').open('a') as l:
        fcntl.flock(l,fcntl.LOCK_EX|fcntl.LOCK_NB)
        grant=load(P/'results/A11-screen-grant');need(grant['plan']==REG and grant['runner']==sha(__file__) and grant['all_h1_and_h4_forms_verified'] and (P/'results/a11-pilot-v3.rc').read_text().strip()=='0','unbound inputs or unfinished qualification')
        need(not ROOT.exists(),'new single-use screen evidence');ex=expected();ROOT.mkdir();dump(ROOT/'expected.json',ex);machine=env_summary();need(machine['mount'].startswith('ext4') and machine['loadavg'][0]<10,('outside host load',machine));dump(ROOT/'host-before.json',machine)
        final={k:[] for k in ('dirty','fresh')}
        for ed in registered()['endpoint_order']:
            prepost('pre',ed,[('starting-original',False),('starting-original-fresh',False)])
            for z in registered()['schedule'][ed]:
                n=z['pair'];edit=n%2==1;rev='edited' if edit else 'original';label=f'pair-{n:02}'
                for arm in z['order']:mark(state(ed,NAME[arm]),fixture(ed),edit)
                for kind in ['dirty','fresh']:
                    for slot,arm in enumerate(z['order'],1):
                        exec_host('run',ed,arm,kind,label,rev);elapsed=load(where(ed,arm,kind,label)/'invocation.json')['elapsed_ns']
                        final[kind].append({'endpoint':ed,'direction':z['direction'],'pair':n,'slot':slot,'arm':arm,'elapsed_ns':elapsed})
                for kind in ['dirty','fresh']:
                    for arm in z['order']:exec_host('audit',ed,arm,kind,label,rev)
                dump(ROOT/ed/(label+'.json'),{'complete':True,'free_bytes':floors(),'loadavg':os.getloadavg()});print(ed,label,'verified',flush=True)
            prepost('post',ed,[('final-edited',True),('final-edited-fresh',True),('final-original',False),('final-original-fresh',False)])
        for k,v in final.items():export_rows(k,v)
        dump(ROOT/'host-after.json',env_summary());dump(ROOT/'complete.json',{'plan':REG,'runner':sha(__file__),'dirty_csv':sha(ROOT/'dirty.csv'),'fresh_csv':sha(ROOT/'fresh.csv'),'commands_timed':64})
