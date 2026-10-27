"""Execute the preregistered full Ruff comparison only after all earlier host cohorts and local gates pass."""
import argparse,csv,fcntl,os,shutil,subprocess,sys,time,traceback
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parent))
from common import P,PIN,RUFF,FROZEN,CARGO_HOME,SONAME,load,dump,sha,git,need
from witness import as_digest
from namespace import skeleton,cargo_home,spawn_args

H=Path(__file__).resolve().parent; PLAN=H/'ruff-prefetch-registration.json'; REG='9b0e4509b59703a7d6d3f517990067dd0d3b980ed7d97ba98253927099401eae'
B=Path.home()/'.cache/ohm-233-position-qualified-20261027'; prior=B/'cargo-observer-ruff-final'
cli=argparse.ArgumentParser(description=__doc__);cli.add_argument('--subjects',type=Path,required=True);cli.add_argument('--driver',type=Path,required=True);cli.add_argument('--out',type=Path,default=B/'whole-ruff-observer-prefetch-fifo-v1');args=cli.parse_args();out=args.out.resolve();imgs=args.subjects.resolve();plan=load(PLAN);subject=plan['subjects'];driver=args.driver.resolve()
def free():need(shutil.disk_usage(out).free>25*2**30,('H2 dedicated home reserve',out))
def source_ok():need(git('rev-parse','HEAD')==PIN and not git('status','--porcelain'),'Ruff must be clean and pinned')
def validate_files():
    need(sha(PLAN)==REG,'registration digest');need(sha(H/'combined.patch')==subject['source_changes']['combined_patch_sha256'],'source');need(sha(driver)==subject['compiler_driver_sha256'],'compiler');need(sha(FROZEN/'bin/rustc')==subject['rustc_sha256'],'frontend');
    need(sha(imgs/'verify-obs1')=='42cfe5b2d040674cc7d99a372d712a8919136090208a0d07436eaef57f8c7337','OBS1 helper')
    for d,n in [('V','cargo_control'),('C','cargo_candidate')]:
        need(sha(imgs/d)==subject[n]['sha256'],'Cargo '+d);sdk=load(H/(d+'-sdk-control.json'));actual=load(H/(d+'-two-edits.json'));need(sdk['exact_cargo']==actual['cargo']==subject[n]['sha256'] and sdk['mtime_equal'] and sdk['size_equal'] and sdk['empty']==sdk['warm']!=sdk['before'],'local SDK gates');need(set(actual['endpoints'])=={'add','remove'} and all(x['products']==x['empty'] and not x['repeat_jobs'] for x in actual['endpoints'].values()),'local true edits')
    for arm, name in [('V','guardv3'),('C','stackv5')]:
        r=load(H/(name+'.fifo.json'));need(r['cargo_sha256']==sha(imgs/arm) and r['no_writer_ever'] and not r['timed_out_in_open'] and r['programs_equal'] and r['command_returncode']!=0 and r['open_flags'] and all(flags & os.O_NONBLOCK and flags & os.O_NOCTTY for flags in r['open_flags']),'FIFO barrier '+arm)
        need(not r['symlink'][-1] and r['downgrade']['cargo_sha']==plan['amends']['matching_legacy_for_controls']['cargo_sha256'] and r['downgrade']['return'][-1]==[],'FIFO symlink/downgrade '+arm)
    leg=load(H/'parent253.fifo.json');need(leg['cargo_sha256']==plan['amends']['matching_legacy_for_controls']['cargo_sha256'] and leg['no_writer_ever'] and not leg['timed_out_in_open'] and not leg['open_flags'] and leg['programs_equal'],'legacy control')
    need(not sys.flags.optimize,'Python asserts disabled')
    for line in (H/'SHA256SUMS').read_text().splitlines():
        digest,name=line.split('  ',1);p=Path(name);need(not p.is_absolute() and '..' not in p.parts and sha(H/p)==digest,('harness digest',p))

def same(a,b):return all(a[k]==b[k] for k in ('elf','executables','raw_sha256','stamps','proofs','roster_sha256','message_sha256','cache_inventory','diagnostics'))

def complete_gates():
    for p in [B/'qualification-posobs4fmt-c3/complete.json',prior/'complete.json',B/'stdlib-holdout-exact-v1/complete.json']:
        need(p.is_file(),('outstanding prerequisite',p))
    need((B/'stdlib-holdout-v1/queue.rc').read_text().strip()=='0','stdlib holdout incomplete')
    need((B/'queue-cargo-ruff-v2.rc').read_text().strip()=='0','prior full Cargo study incomplete')

bad={k for k in os.environ if k in {'MAKEFLAGS','CARGO_MAKEFLAGS','MFLAGS','RUSTFLAGS','RUSTC','RUSTC_WRAPPER','RUSTC_WORKSPACE_WRAPPER','RUSTC_LOG','RUSTC_BOOTSTRAP','RUSTUP_TOOLCHAIN','CARGO_ENCODED_RUSTFLAGS','CARGO_INCREMENTAL','CARGO_BUILD_RUSTFLAGS','CARGO_BUILD_RUSTC','CARGO_BUILD_RUSTC_WRAPPER','CARGO_BUILD_RUSTC_WORKSPACE_WRAPPER','CARGO_BUILD_TARGET','CARGO_TARGET_X86_64_UNKNOWN_LINUX_GNU_LINKER'} or k.startswith(('WILD_','CARGO_PROFILE_'))};need(not bad,('unexpected environment',bad))
complete_gates();validate_files()
with (P/'native-measure.lock').open('a') as lock:
    fcntl.flock(lock,fcntl.LOCK_EX);complete_gates();source_ok();need(out.parent.stat().st_dev==Path.home().stat().st_dev and not out.exists(),('use new H2 home path',out));out.mkdir();free();index=Path(git('rev-parse','--path-format=absolute','--git-path','index'));first_index=sha(index)
    try:
        mount=skeleton(out);original={m:prior/'state'/m/'candidate' for m in ['build','test']};cache={};extras={};anchors={};results={};
        for mode in ['build','test']:
            need(all((original[mode]/p).is_dir() for p in ('registry-home','target','shared')),('retained store missing',mode));cache[mode]=out/('cargo-home-'+mode);extras[mode]=cargo_home(cache[mode],original[mode]/'registry-home')
        def go(mode,arm,phase,label,ref=None,st=None):
            free();dest=out/label;base=spawn_args(mount,out,st or original[mode],cache[mode],extras[mode],imgs/arm,driver)
            cmd=[*base,sys.executable,'-B',str(H/'worker.py'),arm,mode,phase,str(dest),str(imgs/'verify-obs1')];
            if ref:cmd+=['--ref',str(ref)]
            subprocess.run(cmd,check=True);return load(dest/'receipt.json')
        dump(out/'subjects.json',dict(plan=REG,subjects=subject,source_index=first_index,physical_stores={m:str(p) for m,p in original.items()},cpu='0-23',jobs=8,trust={'native':'all','proc_macro':'all'},helper=sha(imgs/'verify-obs1')))
        for mode in ['build','test']:
            previous={}
            for n in ['cold','training','preflight']:
                prev=load(prior/mode/'candidate'/n/'receipt.json');previous[n]={k:prev[k] for k in ['elapsed_ns','units','dirty','rustc','linkers','cargo','driver']};
            dump(out/('prior-unscored-'+mode+'.json'),previous)
            # The registry selector includes embedded Cargo commit; a new identical logical home
            # is primed outside timing in both arms before validating the shared trained snapshot.
            for arm in 'VC':go(mode,arm,'prepare','prepare-'+mode+'-'+arm)
            for arm in 'VC':go(mode,arm,'anchor','anchor-'+mode+'-'+arm)
            a=load(out/('anchor-'+mode+'-V')/'anchor.json');b=load(out/('anchor-'+mode+'-C')/'anchor.json');need(same(a,b),('unequal shared anchors',mode));anchors[mode]=out/('anchor-'+mode+'-V')/'anchor.json'
        for tag in ('timed','audit'):
            for block in plan['orders']:
                for mode in block['endpoint_order'].split(','):
                    for arm in block[mode]:
                        name=f"{tag}-{block['block']:02d}-{mode}-{arm}";results[name]=go(mode,arm,tag,name,anchors[mode])
                print(tag,block['block'],flush=True)
        for mode in ['build','test']:
            for arm in 'VC':
                p='final-'+mode+'-'+arm;go(mode,arm,'final',p,anchors[mode]);need(same(load(anchors[mode]),load(out/p/'anchor.json')),('final full digest mismatch',mode,arm))
        need(len(results)==128,'all timings/replays');source_ok();need(first_index==sha(index),'changed Git index');dump(out/'measured.json',{'all':len(results),'source_clean':True,'index':first_index})
        # One complete private copy at a time. The original qualified target is never untrained.
        def recover(arm):
            src=original['test'];stage=out/('recovery-private-'+arm);stage.mkdir();moved=[]
            for name in ('target','shared'):
                source=src/name;dest=stage/name
                estimate=int(subprocess.check_output(['du','-sb',str(source)]).split()[0]);need(shutil.disk_usage(stage).free>25*2**30+estimate,('training copy reserve',name,estimate));subprocess.run(['cp','-a','--reflink=auto','--',str(source),str(dest)],check=True);moved.append(name)
            free();prime=go('test',arm,'prepare','recovery-settle-'+arm,st=stage)
            pp=go('test',arm,'anchor','recovery-anchor-'+arm,st=stage);ra=load(out/('recovery-anchor-'+arm)/'anchor.json');need(len(ra['proofs'])==1,'recovery observer');logical=Path(ra['proofs'][0]['encoded']);
            from common import TARGET,SHARED
            prefix=next((p for p in (TARGET,SHARED) if logical.is_relative_to(p)),None);need(prefix is not None,'root');physical=stage/('target' if prefix==TARGET else 'shared')/logical.relative_to(prefix);need(physical.name=='dep-lib-ron' and physical.is_file() and physical.is_relative_to(stage),'training file');physical.unlink()
            steps=[]
            for i in range(1,5):
                rr=go('test',arm,'train',f'recovery-{arm}-{i}',st=stage);steps.append({'step':i,'ns':rr['ns'],'dirty':rr['dirty'],'physical':rr['processes'],'proofs':rr['training_proof_state']})
                if not rr['dirty'] and not rr['processes']['rustc'] and any(z['complete'] for z in rr['training_proof_state']):break
            end='recovery-final-'+arm;go('test',arm,'anchor',end,st=stage);final=load(out/end/'anchor.json');need(final['raw_sha256']==ra['raw_sha256'],'recovery native outputs changed');need(steps[-1]['dirty']==[] and any(x['dirty'] for x in steps),'missing-observer recovery uncontrolled');dump(out/('training-'+arm+'.json'),steps)
            # These are the disposable independent reproduction copies; keep every input and receipt
            # needed to recreate them, and the immutable original dataset. Remove no other path.
            for n in moved:
                p=stage/n;need(p.parent==stage and stage.parent==out and n in {'target','shared'} and not p.is_symlink(),'checked private cleanup');shutil.rmtree(p)
        try:
            for arm in 'VC':recover(arm)
        except Exception as e:
            dump(out/'training-limit.json',{'error':repr(e)});print('Unscored training limitation:',repr(e),flush=True)
        source_ok();validate_files();need(first_index==sha(index),'changed Git index');dump(out/'complete.json',{'timed':64,'audited':64,'source_clean':True,'index':first_index,'training_limit':(out/'training-limit.json').is_file()})
    except BaseException:
        (out/'failure.txt').write_text(traceback.format_exc());raise
