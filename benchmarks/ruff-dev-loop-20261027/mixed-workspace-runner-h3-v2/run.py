"""Qualify cold/full/guarded mixed libraries, then run the separately authorized native edit schedule."""
import argparse, csv, fcntl, hashlib, json, os, shutil, signal, subprocess, sys, traceback
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
from common import P, RUFF, TARGET, SHARED, CARGO_HOME, FROZEN, dump, load, need, sha
from state import H, BASE, PLAN, PLAN_SHA, WASM, BUDGET, gate_free, verify_plan, source_clean, inputs, seed, set_source, source_binds
from namespace import skeleton, spawn_args
from products import compare_context
from h3_host import check_h3

cli=argparse.ArgumentParser();cli.add_argument('--binding',type=Path,required=True);cli.add_argument('--release',type=Path,required=True);cli.add_argument('--out',type=Path,required=True);cli.add_argument('--phase',choices=['qualify','score'],required=True)
a=cli.parse_args(); out=a.out.resolve(); binding=a.binding.resolve(); b=load(binding); release=load(a.release); plan=H/'plan.json'; phase=a.phase
need(release['binding_sha256']==sha(binding) and release['permission']==phase and release['url'].startswith('https://github.com/astral-sh/ohm-cargo/'),'explicit release binding')
verify_plan();need(b['plan_sha256']==PLAN_SHA and b['arm_order']==PLAN['endpoints'],'binding order')
need(b['cargo_base']==PLAN['base_cargo_pgo'] and b['driver_base']==PLAN['base_compiler_driver'] and b['arms']['A']['cargo_sha256']==b['arms']['C']['cargo_sha256']!=b['arms']['B']['cargo_sha256']==b['cargo_base'] and b['arms']['B']['driver_sha256']==b['arms']['C']['driver_sha256']!=b['arms']['A']['driver_sha256']==b['driver_base'],'wrong ablations')
for tag,record in b['arms'].items():
    for key in ('cargo','driver'):need(sha(Path(record[key]))==record[key+'_sha256'],('subject data',tag,key))
for seq,n in [(b['host']['host_tools'], 'host')]:
    for key,v in seq.items():need(Path(v['path']).resolve()==Path(v['resolved']) and sha(Path(v['path']))==v['sha256'],('host tool',key))
for k,v in b['runner_inputs'].items():need(sha(H/k)==v,('runner source changed',k))
need(out.parent==BASE and b['storage']['new_result_path']==str(out) and out.parent.stat().st_dev==b['host']['physical_state_parent']['device_number'],'physical storage')
def gates():
    check_h3(b)
    for path in b['prerequisite_rc']:need(Path(path).read_text().strip()=='0',('prerequisite did not complete',path))
    for path in b['prerequisite_json']:need(isinstance(load(Path(path)),dict),('missing qualification',path))
    need(any('corrected-native-rerun' in p for p in b['prerequisite_rc']), 'expected corrected native qualification')
    need(any('prefetch-fifo-qualified' in p for p in b['prerequisite_rc']), 'expected earlier no-op study')
    need(len(b['reviewed_safety_sha256'])>=3 and all(len(v)==64 for v in b['reviewed_safety_sha256'].values()), 'independent export/ordering/env/FIFO controls')
gates()
def dest(mode,tag,name):return out/'receipts'/mode/tag/name
def state(mode,tag):return out/'state'/mode/tag
def persist(name,value):dump(out/name,value)
def checked_launch(cmd):
    p=subprocess.Popen(cmd,start_new_session=True)
    try:
        while True:
            try:p.wait(timeout=3);break
            except subprocess.TimeoutExpired:gate_free(out)
        need(p.returncode==0,('worker returned',p.returncode,cmd[-11:]))
    except BaseException:
        if p.poll() is None:os.killpg(p.pid,signal.SIGTERM);p.wait(timeout=30)
        raise
    gate_free(out)

def command(st,arm,extra=()):
    subject=b['arms'][arm];prefix=spawn_args(mount,out,st,st/'registry-home',[],Path(subject['cargo']),Path(subject['driver']));at=prefix.index('--')
    return [*prefix[:at],*source_binds(st),*extra,*prefix[at:]]
def call(mode,state_tag,arm,level,name,edit,force=None):
    st=state(mode,state_tag);d=dest(mode,state_tag,name);d.parent.mkdir(exist_ok=True,parents=True);need(not d.exists(),('duplicate command',d))
    set_source(st,fixture,edit);cmd=[*command(st,arm),sys.executable,'-B',H/'worker.py','--arm',arm,'--mode',mode,'--state','edited' if edit else 'original','--phase',level,'--out',str(d),'--manifest',str(fixture/'manifest.json'),'--binding',str(binding)]
    if force:cmd+=['--force-from',str(force/'receipt.json')]
    known=st/'recorded-recipe-paths.json'
    if known.is_file():cmd+=['--known-recipes',str(known)]
    checked_launch(cmd);row=load(d/'receipt.json')
    if not known.exists() and (arm!='C' or len(row['recipe_after'])>=2):dump(known,sorted(row['recipe_after']))
    return row
def train(mode,tag,arm,edited=False):
    first=call(mode,tag,arm,'cold','cold',edited);need(first['product']['dirty'],'cold state')
    for i in range(1,5):
        row=call(mode,tag,arm,'train',f'train-{i}',edited)
        if row['fresh_units']==row['unit_count'] and not row['processes']['jobs']:break
    else:raise ValueError(('training never settled',mode,tag))
    fresh=call(mode,tag,arm,'detailed-fresh','initial-fresh',edited)
    need(fresh['product']['structural_roster']==first['product']['structural_roster'],'changed initial roster')
    return first,fresh

def check_row(r,ref):
    need(r['product']['structural_roster']==ref['product']['structural_roster'] and r['product']['messages']==ref['product']['messages'] and r['product']['diagnostics']==ref['product']['diagnostics'], ('own state/diagnostics changed',r['arm'],r['mode'],r['state']))

def storage_bytes(path):return int(subprocess.check_output(['du','-s','-B1',path]).split()[0])
def remove_ephemeral(st,tag):
    need(st.parent.parent==out/'state' and st.name==tag and (tag.startswith('gold-') or tag=='forced-C') and not st.is_symlink(),'private disposable path')
    for n in ('target','shared','registry-home','rustup','inputs'):
        p=st/n;need(p.parent==st and p.is_dir() and not p.is_symlink(),('private reconstructed directory',p));shutil.rmtree(p)

def current_rows(d):return [json.loads(s) for s in (d/'stdout').read_bytes().splitlines() if s]
def clone(mode,event):
    src=state(mode,'C');st=state(mode,'forced-C');gate_free(out,int(storage_bytes(src)*1.12));need(not st.exists(),st)
    subprocess.run(['cp','-a','--reflink=auto','--',src,st],check=True)
    index={}
    for row in current_rows(event):
        if row.get('reason')!='compiler-artifact':continue
        for path in map(Path,row['filenames']):
            unit=next((n for n,p in [('target',TARGET),('shared',SHARED)] if path.is_relative_to(p)),None)
            need(unit is not None,('external advertised file',path))
            rel=path.relative_to(TARGET if unit=='target' else SHARED);base=src/unit/rel;copy=st/unit/rel
            need(base.is_file() and copy.is_file() and not base.samefile(copy),('private output not copied',base,copy))
            key=str(path)
            if key not in index:
                left,right=base.stat(),copy.stat()
                need((left.st_size,left.st_mtime_ns,left.st_mode,sha(base))==(right.st_size,right.st_mtime_ns,right.st_mode,sha(copy)),('output clone mismatch',path))
                index[key]={'sha256':sha(base),'mode':left.st_mode,'mtime_ns':left.st_mtime_ns,'different_inodes':True}
    need(len(index)>=PLAN['endpoints'][mode]['expected_units'],('incomplete clone inventory',mode,len(index)))
    dump(out/('cloned-artifacts-'+mode+'.json'),index)
    return st

def bridge(mode,label,audits):
    rows=[];base=out/'bridges'/mode/label;base.mkdir(parents=True)
    for cr in WASM:
        artifacts={}
        for arm in 'BC':
            d=base/(cr+'-bridge-'+arm);d.mkdir();st=state(mode,arm);reference=audits[arm]
            args=command(st,arm,['--bind',str(d),str(out/'bridge-canonical')])
            checked_launch([*args,sys.executable,'-B',H/'bridge_worker.py','--action','bridge','--crate',cr,'--arm',arm,'--root',out,'--out',d/'receipt','--binding',binding,'--details',reference/'receipt.json','--flags',dest(mode,arm,'cold')/'receipt.json'])
            artifacts[arm]=d/'libordinary_bridge.rlib';need(artifacts[arm].is_file(),('missing bridge',arm,cr))
        values=set()
        for built,file in artifacts.items():
            for arm in 'BC':
                d=base/(cr+'-caller-'+built+'-'+arm);d.mkdir();st=state(mode,arm)
                args=command(st,arm,['--bind',str(d),str(out/'bridge-canonical'),'--ro-bind',str(file),str(out/'libordinary_bridge_input.rlib')])
                checked_launch([*args,sys.executable,'-B',H/'bridge_worker.py','--action','caller','--crate',cr,'--arm',arm,'--root',out,'--out',d/'receipt','--binding',binding,'--details',audits[arm]/'receipt.json','--flags',dest(mode,arm,'cold')/'receipt.json'])
                result=load(d/'receipt/bridge.json');values.add(result['runtime']);rows.append({'bridge_compiled_using':built,'current_inputs_from':arm,**result})
        need(len(values)==1,('inconsistent runtime on interchangeable producer',cr,values))
    dump(base/'summary.json',rows)
def qualify(mode):
    refs={};logs={};first={};failures={}
    def checked(label,current,reference):
        try:return compare_context(current,reference)
        except ValueError as err:
            note=str(err);failures[label]=note[:1200]
            (out/('oracle-mismatch-'+mode+'-'+label+'.txt')).write_text(note+'\n')
            return {'qualified':False,'mismatch':note[:1200]}
    for arm in 'ABC':
        st=seed(state(mode,arm),fixture,CARGO_HOME);first[arm],ref=train(mode,arm,arm);refs[arm]=ref['product']
        for edited,name in [(True,'edit'),(False,'restore')]:
            warm=call(mode,arm,arm,'conditioning','condition-'+name,edited)
            settled=call(mode,arm,arm,'detailed-fresh','condition-'+name+'-fresh',edited)
            check_row(settled,warm)
    for arm in 'AB':
        tag='gold-'+arm;st=seed(state(mode,tag),fixture,CARGO_HOME);_,cold=train(mode,tag,arm,True)
        refs['edited-'+arm]=cold['product'];remove_ephemeral(st,tag)
    clone(mode,dest(mode,'C','condition-restore-fresh'))
    logs['force']={};logs['independent_cold']={}
    for arm in 'ABC':
        ed=call(mode,arm,arm,'edit','first-edit',True);check=call(mode,arm,arm,'fresh','first-edit-fresh',True);check_row(check,ed)
        logs['independent_cold'][arm]=checked('cold-'+arm,ed['product'],refs['edited-'+('A' if arm=='A' else 'B')])
    force=call(mode,'forced-C','C','forced','forced-edit',True,force=dest(mode,'C','condition-restore-fresh'))
    check=call(mode,'forced-C','C','fresh','forced-edit-fresh',True);check_row(check,force)
    logs['force']['edited']=checked('same-state-edit',load(dest(mode,'C','first-edit')/'receipt.json')['product'],force['product'])
    bridge(mode,'forward',{arm:dest(mode,arm,'first-edit') for arm in 'BC'})
    for arm in 'ABC':
        back=call(mode,arm,arm,'edit','first-restore',False);check=call(mode,arm,arm,'fresh','first-restore-fresh',False);check_row(check,back)
        logs['independent_cold']['restored-'+arm]=checked('restored-'+arm,back['product'],refs[arm])
    force=call(mode,'forced-C','C','forced','forced-restore',False,force=dest(mode,'forced-C','forced-edit'))
    check=call(mode,'forced-C','C','fresh','forced-restore-fresh',False);check_row(check,force)
    logs['force']['restored']=checked('same-state-restore',load(dest(mode,'C','first-restore')/'receipt.json')['product'],force['product'])
    bridge(mode,'reverse',{arm:dest(mode,arm,'first-restore') for arm in 'BC'})
    logs['mismatches']=failures;persist('qualification-'+mode+'.json',logs)
    need(not failures,('preflight collected unqualified cold/forced evidence',failures))
    remove_ephemeral(state(mode,'forced-C'),'forced-C')

def score(mode):
    path=out/(mode+'.csv');need(not path.exists(),'scores already exist')
    refs={arm:{edit:load(dest(mode,arm,'first-edit' if edit else 'first-restore')/'receipt.json') for edit in (True,False)} for arm in 'ABC'}
    for arm in 'ABC':check_row(call(mode,arm,arm,'fresh','score-entry',False),refs[arm][False])
    with path.open('x',newline='') as f:
        w=csv.writer(f);w.writerow(['block','slot','arm','elapsed_ns']);f.flush()
        for i,order in enumerate(PLAN['endpoints'][mode]['orders'],1):
            for slot,arm in enumerate(order,1):
                sample=call(mode,arm,arm,'ordinary',f'block-{i:02d}-edit',True)
                fre=call(mode,arm,arm,'fresh',f'block-{i:02d}-edited-fresh',True);check_row(fre,refs[arm][True])
                call(mode,arm,arm,'settle',f'block-{i:02d}-restore',False)
                fre=call(mode,arm,arm,'fresh',f'block-{i:02d}-restored-fresh',False);check_row(fre,refs[arm][False])
                w.writerow([i,slot,arm,sample['elapsed_ns']]);f.flush()
            print(mode,i,''.join(order),flush=True)
    repeat={}
    for arm in 'ABC':
        for flag,name in [(True,'edit'),(False,'restore')]:
            end=call(mode,arm,arm,'edit','final-'+name,flag);fre=call(mode,arm,arm,'fresh','final-'+name+'-fresh',flag);check_row(fre,end);check_row(fre,refs[arm][flag])
            repeat[arm+'-'+name]=compare_context(end['product'],refs[arm][flag]['product'])
            old=refs[arm][flag]['processes'];new=end['processes']
            brief=lambda q:sorted((j['crate'],j['kind']) for j in q['jobs'])
            need(brief(old)==brief(new),'first/final physical crate roster changed')
    persist('final-'+mode+'.json',repeat)

with (P/'native-measure.lock').open('a') as lock:
    fcntl.flock(lock,fcntl.LOCK_EX);gates();source_hash=source_clean();need(source_hash==b['host']['source_index_sha256'],'staged Ruff index changed')
    if phase=='qualify':
        need(not out.exists(),('new private experiment required',out));out.mkdir(mode=0o700);gate_free(out,b['storage']['expected_increment_bytes'])
    else:
        need((out/'preflight-complete.json').is_file() and not (out/'failure.txt').exists(),'preflight is incomplete or failed')
        pf=load(out/'preflight-complete.json');need(pf['index_sha256']==source_hash and pf['binding']==sha(binding),'source or subjects changed')
        gate_free(out,b['storage']['post_training_headroom_bytes'])
    try:
        if phase=='qualify':
            mount=skeleton(out);persist('mount.json',mount);fixture=inputs(out)
            d=out/'bridge-src';d.mkdir();(out/'bridge-canonical').mkdir();(out/'libordinary_bridge_input.rlib').touch()
            for cr,query in [('ruff_wasm','ruff_wasm::Workspace::version()'),('ty_wasm','ty_wasm::version()')]:
                (d/(cr+'.rs')).write_text('pub fn observed() -> String { '+query+'.to_string() }\n')
            (d/'caller.rs').write_text('fn main() { println!("{}", ordinary_bridge::observed()); }\n')
            for mode in ('build','test'):qualify(mode)
            need(source_clean()==source_hash,'source changed');persist('preflight-complete.json',{'index_sha256':source_hash,'binding':sha(binding),'source_fixture':sha(fixture/'manifest.json'),'free_bytes':gate_free(out)})
        else:
            mount=load(out/'mount.json');fixture=out/'fixture'
            for mode in ('build','test'):score(mode)
            cp=subprocess.run([sys.executable,'-B',H/'analyze.py',plan,out/'build.csv',out/'test.csv'],capture_output=True,check=True)
            persist('statistics.json',json.loads(cp.stdout));need(source_clean()==source_hash,'source changed');persist('complete.json',{'index_sha256':source_hash,'binding':sha(binding),'native_edits':108,'no_exclusions':True,'free_bytes':gate_free(out)})
    except BaseException:
        (out/'failure.txt').write_text(traceback.format_exc());raise

