"""Replay the frozen four-command blocks against independently warmed historical native targets."""
from pathlib import Path
import collections,csv,hashlib,importlib.util,json,os,shutil,subprocess,sys,tempfile,time
here=Path(__file__).resolve().parent
base=here.parent
plan=json.loads((here/'plan-v2.json').read_bytes())
assert hashlib.sha256((here/'plan-v2.json').read_bytes()).hexdigest()=='fd5dfbb9bb8d64ffa5de9d173edc34e25bedef0fd82df0044988fd91ff69e9ea'
assert os.uname().nodename==plan['host']
sys.path.insert(0, str(here))
from diagnostics import diagnose
def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':')).encode()).hexdigest()
def same(path,other):
    if path.exists():assert path.read_bytes()==other
    else:path.write_bytes(other)
def expected_semantics(phase):
    for text,(rc,out,err) in phase.items():
        if text.startswith('raise from'):assert rc==1 and 'byte range 6..10' in err
        else:assert rc==0 and out
def full_receipt(rec):
    j=json.loads((rec/'receipt.json').read_bytes());files=json.loads((rec/'elf-sections.json').read_bytes());sections={}
    for f,sects in files.items():
        n=Path(f).name;assert n not in sections
        sections[n]={k:v for k,v in sects.items() if k not in ('.strtab','.note.gnu.build-id')}
    semantics=json.loads((rec/'semantic.json').read_bytes());expected_semantics(semantics)
    diagnostics=diagnose(j['diagnostics'])
    return dict(sections_sha256=digest(sections),diagnostics_sha256=diagnostics['messages_and_all_notes_sha256'],diagnostics_raw_sha256=diagnostics['full_raw_messages_sha256'],lint_note_locations=diagnostics['spanless_note_locations'],diagnostics=len(j['diagnostics']),semantics_sha256=digest(semantics),units=j['units'],dirty=len(j['dirty']),products=len(j['executables']),raw_elf={Path(k).name:v for k,v in sorted(j['executables'].items())},full=sum(not x[1] for x in j['rustcs']),link_only=sum(x[1] for x in j['rustcs']),api=sorted(j['parser_api'].values()),elapsed_ns=j['elapsed_ns'])
arms={'A':'control','B':'candidate'}
ref={}
for arm in arms.values():
    for phase in ('late-original','late-edited'):
        for mode in ('build','test'):
            ref[arm,phase,mode]=full_receipt(base/'history'/f'{arm}-{phase}-{mode}')
            a,b=(3,0) if arm=='control' and mode=='build' else (7,0) if arm=='control' else (1,1) if mode=='build' else (1,4)
            p=ref[arm,phase,mode]
            assert p['units']==plan['endpoint_units'][mode] and p['products']==(1 if mode=='build' else 5)
            assert (p['full'],p['link_only'])==((0,0) if phase=='late-original' else (a,b))
for mode in ('build','test'):
    for phase in ('late-original','late-edited'):
        x,y=(ref[a,phase,mode] for a in arms.values())
        for k in ('sections_sha256','diagnostics_sha256','semantics_sha256','units','products','dirty'):assert x[k]==y[k],(mode,phase,k,x[k],y[k])
original_argv=sys.argv[:];mods={}
for a,arm in arms.items():
    sys.argv=[str(here/'runtime.py'),arm,'score']
    spec=importlib.util.spec_from_file_location('runtime_'+a,here/'runtime.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);mods[a]=m
sys.argv=original_argv
if sys.argv[1:]==['verify-inputs']:
    (here/'guard-references.json').write_text(json.dumps({'/'.join(k):v for k,v in ref.items()},indent=2,sort_keys=True)+'\n');print('all original and edited references agree on all required ELF, diagnostic and CLI gates')
    sys.exit(0)
assert not sys.argv[1:] and not (here/'started.json').exists()
(here/'started.json').write_text(json.dumps({'utc':time.strftime('%FT%TZ',time.gmtime()),'plan':hashlib.sha256((here/'plan-v2.json').read_bytes()).hexdigest(),'replay':hashlib.sha256((here/'replay.py').read_bytes()).hexdigest(),'runtime':hashlib.sha256((here/'runtime.py').read_bytes()).hexdigest()})+'\n')
for i,b in enumerate(plan['blocks'],1):
    mode=b['endpoint']
    for pos,a in enumerate(b['order'],1):
        arm=arms[a];s=mods[a];prefix=f'b{i:02d}-p{pos}'
        with tempfile.TemporaryDirectory(dir=s.work) as tmp:
            store=Path(tmp);subprocess.run(['cp','-a',str(s.seed)+'/.',store],check=True)
            for moment,src,phase in [('fresh',s.src,'late-original'),('edited',s.altered,'late-edited')]:
                tag=prefix+'-'+moment;s.run(store,src,mode,tag);rec=s.out/(arm+'-'+tag+'-'+mode)
                obs=full_receipt(rec);gold=ref[arm,phase,mode]
                for k in ('units','products','dirty','sections_sha256','diagnostics_sha256','semantics_sha256','full','link_only','api'):
                    if obs[k]!=gold[k]:raise RuntimeError((i,pos,a,mode,moment,k,obs[k],gold[k]))
                row={'block':i,'endpoint_block':b['within_endpoint'],'order':b['order'],'position':pos,'arm':a,'mode':mode,'phase':moment,**obs}
                with (here/'rows.jsonl').open('a') as r:r.write(json.dumps(row,separators=(',',':'))+'\n')
    print('qualified block',i,mode,b['order'],flush=True)
(here/'completion.json').write_text(json.dumps({'utc':time.strftime('%FT%TZ',time.gmtime()),'guarded_rows':sum(1 for _ in (here/'rows.jsonl').open())})+'\n')
