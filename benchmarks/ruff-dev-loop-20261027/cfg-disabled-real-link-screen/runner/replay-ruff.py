"""Pre-timing, traced unqualified workspace test builds for the Cargo-only cached Rust object path."""
import collections,fcntl,subprocess,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
from shared import *
from elf import elf
from inspect_products import cli,library
from replay_processes import parsed
from roster import audit_json
SHA={'A11':'a0acc664af50231926f1b69bc64fdc02dd7c4fcc7c232f5e70f8ba451a354db4','Stock11':'dd5cab154b8dcd09ccc2753160d314cade80979b2d055ee66aa9e2217e05e7e1'}
phases=[('seed',False),('fresh-seed',False),('edit',True),('fresh-edit',True),('restore',False),('fresh-restore',False),('edit-again',True),('fresh-again',True)]
def compact_elf(path):
    r=elf(path)
    return {k:r[k] for k in ('raw','size','rodata_entsize','gnu_build_id','content_with_two_wild_fields_masked')}
def inside(ed,a,label,st):
    out=P/'results'/ed/a/label;attempted=out.is_dir();out.mkdir(exist_ok=True);edited=st=='edited';view(ed,edited);trusted()
    need(sha(FROZEN/'bin/cargo')==SHA[a] and sha(FROZEN/'lib'/SONAME)==plan()['baseline_rustc'],'product image')
    if attempted:
        need(not (out/'observation.json').exists() and label=='edit' and ed=='wasm-only' and a=='A11' and json.loads((out/'stdout').read_bytes().splitlines()[-1])=={'reason':'build-finished','success':True},'only recover the completed unscored dirty invocation')
    else:
      with (out/'stdout').open('wb') as so,(out/'stderr').open('wb') as se:
        ret=subprocess.run(['strace','-ff','-qq','-s','262144','-e','trace=execve,execveat','-o',str(out/'exec'),*plan()['command']],cwd=WT,env=env(),stdin=subprocess.DEVNULL,stdout=so,stderr=se)
      need(ret.returncode==0,('cargo',out,(out/'stderr').read_text()[-1500:]))
    j=audit_json(out/'stdout','test');r=parsed(out,j);arts=[x for l in (out/'stdout').read_bytes().splitlines() if (x:=json.loads(l))['reason']=='compiler-artifact'];apis={}
    for x in arts:
        if x['target']['kind']!=['test'] or x['target']['name']!='api':continue
        p=Path(x['executable']);c=p.with_suffix('.rlink-cache.json');proof=load(c).get('disabled_test') if c.is_file() else None
        need(proof is None or isinstance(proof,str) and len(proof)==64,('unexpected product proof',proof))
        listing=subprocess.check_output([p,'--list'],env=env(),text=True).strip();need(listing=='0 tests, 0 benchmarks',listing)
        apis[Path(x['manifest_path']).parent.name]={'name':p.name,'raw':sha(p),'source_proof':proof,'test_list':listing}
    names={v['name'] for v in apis.values()};jobs=[x for x in r['rustc'] if x[1]=='api'];links=[x for x in r['native_links'] if x[1] in names]
    need(set(apis)=={'ruff_wasm','ty_wasm'} and not r['native_probes'] and len(jobs)==len(links) and all(x[2] and not x[3] for x in links) and not any(x[4] for x in jobs),('native-protocol mismatch',jobs,links,r))
    if label.startswith('fresh'):need(not j['dirty'] and not r['rustc'] and not r['native_links'],'changed immediate no-op')
    if label in ('restore','edit-again'):
        n=1 if ed=='wasm-only' else 2;mode='link-only' if a=='A11' else 'full'
        need(len(jobs)==n and all(x[2]==mode for x in jobs),('required trained mode',ed,a,label,jobs))
    ruff,={v['executable'] for v in arts if v['target']['name']=='ruff' and v['target']['kind']==['bin'] and not v['profile']['test'] and v['executable']}
    rich=label in ('edit','restore','edit-again')
    data={'cargo':SHA[a],'driver':plan()['baseline_rustc'],'edit':ed,'state':st,'phase':label,'units':j['units'],'executables':len(j['executables']),'elf_count':len(j['elf']),'dirty':j['dirty'],'roster':j['roster_sha256'],'messages':j['message_sha256'],'rustc':r['rustc'],'cc':len(r['cc_with_output']),'collect2':len(r['collect2_with_output']),'wild':r['native_links'],'api':apis,'cli':cli(ruff,ed,edited),'caller':library(arts,ed=='wasm-only' and edited,out) if rich else None,'elfs':{str(Path(n).relative_to(TARGET)):compact_elf(Path(n)) for n in j['elf']} if rich else None}
    need(not rich or len(data['elfs'])==len(j['elf']),'ELF basenames collide')
    dump(out/'observation.json',data);print(ed,a,label,collections.Counter(x[2] for x in r['rustc']),len(r['native_links']),jobs,flush=True)
def prepare(ed,a):
    s=state(ed,a);out=P/'results'/ed/a
    need(not s.exists() and not out.exists(),'require new worktree state')
    seed(ed,a);out.mkdir(parents=True);ref=state('parser','A')
    fresh=load(P/'results/parser/A/cold/receipt.json');need(fresh['units']==619 and fresh['fresh_units']==0,'authentic A cold donor')
    for n in ['target','build']:
        need(not any((s/n).iterdir()),'empty pre-copy state')
        subprocess.run(['cp','-a','--reflink=auto','--',str(ref/n)+'/.',str(s/n)],check=True)
    floors()
def run(ed,a):
    s=state(ed,a);out=P/'results'/ed/a
    for label,edited in phases:
        if (out/label/'observation.json').is_file():continue
        mark(s,fixture(ed),edited);subprocess.run([*shell(ed,a),sys.executable,'-B',__file__,'inside',ed,a,label,'edited' if edited else 'original'],check=True,env=env())
    dump(out/'complete.json',{n:load(out/n/'observation.json') for n,_ in phases})
if sys.argv[1:2]==['inside']:inside(*sys.argv[2:]);sys.exit(0)
with (P/'bench.lock').open('a') as lock:
    fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB);need(not (P/'results/A11-screen-grant').exists(),'must precede scoring')
    for arm,hash in SHA.items():
        if arm=='Stock11' and not (TRANSFER/arm).exists():shutil.copy2(TRANSFER/'A',TRANSFER/arm)
        need(sha(TRANSFER/arm)==hash,arm)
    ed,arm=sys.argv[1:];s=state(ed,arm)
    if s.exists():need((s/'seed.json').is_file() and ed=='wasm-only' and arm=='A11' and not (P/'results'/ed/arm/'complete.json').exists(),'only resume uniquely identified unfinished private preflight')
    else:prepare(ed,arm)
    run(ed,arm)
