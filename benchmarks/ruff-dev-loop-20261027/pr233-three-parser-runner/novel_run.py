"""Unscored, original-first full Ruff controls for three precommitted source patches."""
import argparse, collections, fcntl, os, platform, shutil, signal, subprocess, sys, traceback
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parent))
from common import P, FROZEN, SONAME, RUFF, CARGO_HOME, load, need, dump, sha
from novel_state import H, OUT, BASE, PLAN, PLAN_SHA, PLAN_URL, seed, source_binds, source_clean, verify_plan, set_source, make_fixtures
from namespace import skeleton, spawn_args
from state import WASM
from archive_audit import compare as archive_compare
parser=argparse.ArgumentParser()
parser.add_argument('--release',type=Path,required=True)
args=parser.parse_args()
binding=H/'binding.json';b=load(binding)
need(sha(H/'novel-plan.json')==PLAN_SHA==b['plan_sha256'] and b['plan_url']==PLAN_URL,'pre-exposure identity')
release=load(args.release);need(release=={'binding_sha256':sha(binding),'phase':'unscored-pr233-three-edits','plan_url':PLAN_URL},'independent release/binding')
verify_plan()
need(b['arms']==PLAN['subjects'] and list(sorted(b['arms']))==['B','C'],'frozen treatments')
for rel,val in b['runner'].items():need(sha(H/rel)==val,('changed runner',rel))
need(OUT.parent==BASE and BASE.stat().st_dev==b['host']['physical_state_parent']['device_number'],'wrong store')
need(platform.machine()=='x86_64' and platform.release()==b['host']['kernel'] and os.cpu_count()==32 and sorted(os.sched_getaffinity(0))==list(range(24)), 'H5 topology')
need('charlie-ohm-loader-perf-1024' in platform.node() and not sys.flags.optimize,'host identity')
need(shutil.which('cargo')==str(Path.home()/'.cargo/bin/cargo'),'unexpected rustup proxy')
banned=set('RUSTC RUSTC_WRAPPER RUSTC_WORKSPACE_WRAPPER RUSTC_BOOTSTRAP RUSTC_LOG RUSTUP_TOOLCHAIN RUSTFLAGS CARGO_ENCODED_RUSTFLAGS CARGO_INCREMENTAL CARGO_BUILD_RUSTFLAGS CARGO_BUILD_RUSTC CARGO_BUILD_RUSTC_WRAPPER CARGO_BUILD_RUSTC_WORKSPACE_WRAPPER CARGO_BUILD_TARGET CARGO_TARGET_X86_64_UNKNOWN_LINUX_GNU_LINKER MAKEFLAGS MFLAGS CARGO_MAKEFLAGS'.split())
need(not [k for k in os.environ if k in banned or k.startswith(('PYTHONOPTIMIZE','CARGO_PROFILE_','WILD_'))],'benchmark flag override')
for tag,s in b['arms'].items():
    for key in ('cargo','driver'):need(sha(Path(s[key]))==s[key+'_sha256'],('subject changed',tag,key))
for k,v in b['host']['host_tools'].items():need(Path(v['path']).resolve()==Path(v['resolved']) and sha(Path(v['path']))==v['sha256'],('host tool changed',k))

def capacity(n=25):
    remain=shutil.disk_usage(BASE).free
    need(remain>=n*2**30,('disk reserve GiB',n,remain))
    return remain
def launch(argv,allow_failure=False):
    capacity()
    p=subprocess.Popen(argv,start_new_session=True)
    try:
        while True:
            try:rc=p.wait(timeout=3);break
            except subprocess.TimeoutExpired:capacity()
        capacity()
        if not allow_failure:need(rc==0,('child failed',rc,argv[-7:]))
        return rc
    except BaseException:
        if p.poll() is None:
            os.killpg(p.pid,signal.SIGTERM)
            try:p.wait(timeout=20)
            except subprocess.TimeoutExpired:os.killpg(p.pid,signal.SIGKILL);p.wait(timeout=5)
        raise
def st(mode,arm):return OUT/'state'/mode/arm
def dest(mode,arm,name):return OUT/'receipts'/mode/arm/name
def cmd(mode,arm,extra=()):
    state=st(mode,arm);a=b['arms'][arm];p=spawn_args(mount,OUT,state,state/'registry-home',[],Path(a['cargo']),Path(a['driver']));i=p.index('--')
    return [*p[:i],*source_binds(state),*extra,*p[i:]]
def call(mode,arm,label,phase,name):
    d=dest(mode,arm,name);d.parent.mkdir(parents=True,exist_ok=True);need(not d.exists(),('duplicate case',d))
    set_source(st(mode,arm),fixture,label)
    print(f'{mode} {arm} {name} starting',flush=True)
    launch([*cmd(mode,arm),sys.executable,'-B',H/'novel_worker.py',mode,arm,label,phase,name])
    r=load(d/'receipt.json')
    print(f'{mode} {arm} {name} units {r["fresh_units"]}/{r["unit_count"]}, {r["process_totals"]}, Wild {r["native_totals"]["wild"]}',flush=True)
    return r
def compare_rows(a,b):
    x=a['product'];y=b['product'];need(x['elf'].keys()==y['elf'].keys(),'ELF inventory changed')
    diffs={}
    for name,left in x['elf'].items():
        right=y['elf'][name]
        if left['raw']==right['raw']:continue
        diff={s:[v,right['section_hashes'].get(s)] for s,v in left['section_hashes'].items() if v!=right['section_hashes'].get(s)}
        for s,v in right['section_hashes'].items():
            if s not in left['section_hashes']:diff[s]=[None,v]
        diffs[name]={'raw':[left['raw'],right['raw']],'size':[left['size'],right['size']],'matches_after_gnu_id_and_rodata_entsize_mask':left['content_with_two_wild_fields_masked']==right['content_with_two_wild_fields_masked'],'different_sections':list(diff)}
    output={'same_unit_paths':x['structural_roster']==y['structural_roster'],'same_compiler_messages':x['messages']==y['messages'],'same_old_cli':x['diagnostics']==y['diagnostics'],'same_novel_cli':a['novel_cli']==b['novel_cli'],'elf_count':len(x['elf']),'raw_elf_differences':diffs,'mixed':{}}
    for cr in WASM:
        l,r=x['mixed'][cr],y['mixed'][cr]
        fields=('rmeta_bytes','rmeta_sha256','private_svh','public_svh','stable_crate_id','embedded_object_sha256','root_listing_sha256','exports','zero_byte_allocations','normalized_archive_sha256')
        z={k:[l[k],r[k]] for k in fields if l[k]!=r[k]};la,ra=l['archive'],r['archive']
        if len(la['objects'])==len(ra['objects']):archive=archive_compare(la,ra)
        else:archive={'object_counts_differ':[len(la['objects']),len(ra['objects'])]}
        output['mixed'][cr]={'different_properties':z,'native':archive,'raw_rlibs':[la['sha256'],ra['sha256']],'raw_cdylib':[l['cdylib_elf']['raw'],r['cdylib_elf']['raw']]}
    need(all(output[k] for k in ('same_unit_paths','same_compiler_messages','same_old_cli','same_novel_cli')),('workspace or CLI mismatch',output))
    return output
def immediate(mode,arm,label,changed,name):
    fresh=call(mode,arm,label,'fresh',name+'-fresh');x,y=changed['product'],fresh['product']
    need(x['structural_roster']==y['structural_roster'] and x['messages']==y['messages'] and x['diagnostics']==y['diagnostics'] and changed['novel_cli']==fresh['novel_cli'],('lost immediate workspace witness',mode,arm,label))
    need({k:v['raw'] for k,v in x['elf'].items()}==fresh['raw_fresh_elf'],('fresh output changed bytes',mode,arm,label))
    return fresh
def bridges(mode,name):
    root=OUT/'bridges'/mode/name;root.mkdir(parents=True);summary=[]
    for cr in WASM:
        arts={}
        for arm in 'BC':
            d=root/(cr+'-bridge-'+arm);d.mkdir();argv=[*cmd(mode,arm,['--bind',str(d),str(OUT/'bridge-canonical')]),sys.executable,'-B',H/'bridge_worker.py','--action','bridge','--crate',cr,'--arm',arm,'--root',OUT,'--out',d/'receipt','--binding',binding,'--details',dest(mode,arm,name)/'receipt.json','--flags',dest(mode,arm,'cold')/'receipt.json']
            rc=launch(argv,True);summary.append({'kind':'bridge','input_arm':arm,'crate':cr,'exit':rc})
            if rc==0:arts[arm]=d/'libordinary_bridge.rlib'
        for origin,path in arts.items():
            for arm in (origin,):
                d=root/(cr+'-caller-'+origin+'-'+arm);d.mkdir();extra=['--bind',str(d),str(OUT/'bridge-canonical'),'--ro-bind',str(path),str(OUT/'libordinary_bridge_input.rlib')]
                argv=[*cmd(mode,arm,extra),sys.executable,'-B',H/'bridge_worker.py','--action','caller','--crate',cr,'--arm',arm,'--root',OUT,'--out',d/'receipt','--binding',binding,'--details',dest(mode,arm,name)/'receipt.json','--flags',dest(mode,arm,'cold')/'receipt.json']
                rc=launch(argv,True);summary.append({'kind':'caller','bridge_from':origin,'current_arm':arm,'crate':cr,'exit':rc,'observed':load(d/'receipt/bridge.json') if rc==0 else (d/'receipt/stderr').read_text(errors='replace')[:1000]})
    dump(root/'summary.json',summary)
    need(len(summary)==8 and all(row['exit']==0 for row in summary),('independent same-release Rust reader failed',mode,name,summary))
    return summary
def brief(r):return {k:r[k] for k in ('phase','source_view','unit_count','fresh_units','elf_count','executable_count','process_totals','native_totals')}
def run_mode(mode):
    summary={'scheduling_plan':PLAN_SHA,'cold':{},'first_occurrences':{},'cross_arm':{},'original_vs_own_restores':{},'ordinary_callers':{}}
    initial={}
    for arm in 'BC':
        seed(st(mode,arm),fixture)
        first=call(mode,arm,'original','cold','cold');initial[arm]=first;summary['cold'][arm]=brief(first)
        for i in range(1,5):
            row=call(mode,arm,'original','train',f'original-warm-{i}')
            if row['fresh_units']==row['unit_count'] and not row['processes']['jobs'] and not any(row['native_totals'].values()):break
        else:raise ValueError(('original warm never settled',mode,arm))
        # A first command may construct attestations and rebuild identical sources. Rebind all starting artifacts to the settled pre-edit state.
        current=call(mode,arm,'original','baseline','original-baseline');initial[arm]=current
        immediate(mode,arm,'original',current,'original-baseline')
    summary['cross_arm']['original-baseline']=compare_rows(initial['B'],initial['C'])
    for label in PLAN['schedule']:
        for step,view in (('edit',label),('restore','original')):
            n=label+'-'+step;results={}
            for arm in 'BC':
                results[arm]=call(mode,arm,view,step,n);immediate(mode,arm,view,results[arm],n)
            summary['first_occurrences'][n]={a:brief(r) for a,r in results.items()};summary['cross_arm'][n]=compare_rows(results['B'],results['C'])
            if step=='restore':summary['original_vs_own_restores'][n]={arm:compare_rows(results[arm],initial[arm]) for arm in 'BC'}
            if step=='edit':summary['ordinary_callers'][n]=bridges(mode,n)
            dump(OUT/(mode+'-observations.json'),summary)
    need(source_clean()==source_index,'changed real Git index/worktree');dump(OUT/(mode+'-complete.json'),{'plan_sha256':PLAN_SHA,'result_sha256':sha(OUT/(mode+'-observations.json')),'free_bytes':capacity()})
def setup():
    need(not OUT.exists(),'prior private state would destroy first occurrence');OUT.mkdir(mode=0o700);capacity(40)
    global fixture,mount
    fixture=make_fixtures(OUT);mount=skeleton(OUT)
    d=OUT/'bridge-src';d.mkdir();(OUT/'bridge-canonical').mkdir();(OUT/'libordinary_bridge_input.rlib').touch()
    for cr,q in [('ruff_wasm','ruff_wasm::Workspace::version()'),('ty_wasm','ty_wasm::version()')]:
        (d/(cr+'.rs')).write_text('pub fn observed() -> String { '+q+'.to_string() }\n')
    (d/'caller.rs').write_text('fn main() { println!("{}", ordinary_bridge::observed()); }\n')
with (P/'native-measure.lock').open('r+') as lock:
    fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB);source_index=source_clean()
    need(source_index==b['host']['source_index_sha256'],'real Ruff index changed')
    setup()
    try:
        dump(OUT/'preflight.json',{'plan_sha256':PLAN_SHA,'binding_sha256':sha(binding),'source_index':source_index,'fixture_manifest':sha(fixture/'manifest.json'),'build_entry_free':capacity(40)})
        run_mode('build')
        free=shutil.disk_usage(BASE).free;go=free>=60*2**30;dump(OUT/'test-admission.json',{'free_bytes':free,'required_bytes':60*2**30,'run_independent_test_arms':go})
        if go:run_mode('test')
        need(source_clean()==source_index,'changed real Ruff index');dump(OUT/'complete.json',{'plan_sha256':PLAN_SHA,'source_index_unchanged':source_index,'free_bytes':capacity(),'test_admitted':go})
    except BaseException:
        (OUT/'failure.txt').write_text(traceback.format_exc());raise
