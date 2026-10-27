"""Exercise a full/full reader witness after the H3 gate closed, with all original stores read-only."""
import fcntl,gzip,hashlib,json,os,re,shutil,subprocess,sys,time
from pathlib import Path
x=Path.home()/'.cache/ohm-233-position-qualified-20261027';w=x/'mixed-native-abc-protocol-h3-v2';r=x/'mixed-native-full-abc-h3-v2';s=x/'mixed-h3-v2-rejected'/'readers-real-exitcodes';sys.path.insert(0,str(w));from common import P,TARGET,SHARED,CARGO_HOME,sha,load,dump,need;from namespace import spawn_args;from state import source_binds,source_clean
b=load(w/'runner-binding.json');mount=load(r/'mount.json');base=r/'receipts/build';states=r/'state/build';goldmap={'A':('A','first-edit'),'B':('B','first-edit'),'C':('C','first-edit'),'forced-C':('forced-C','forced-edit'),'gold-B':('gold-B','cold'),'gold-A':('gold-A','cold')};rec=lambda label:base/goldmap[label][0]/goldmap[label][1]/'receipt.json';execs=[];physical={}
def binary(label,cr,key):return load(rec(label))['product']['mixed'][cr][key]
def exported(digest,suffix):
 p=s.parent/'readers-ablation'/'exports'/(digest+suffix)
 if not p.exists():
  with gzip.open(r/'retained-mixed'/(digest+'.gz'),'rb') as a,p.open('xb') as z:shutil.copyfileobj(a,z)
 need(sha(p)==digest,('archived output',digest));return p

def cmd(case,act,cr,state,graph,brid=None):
 d=s/case;d.mkdir();orig_src=load(rec(graph))['product']['mixed'][cr];current=load(rec(state))['product']['mixed'][cr];arm='C' if state=='forced-C' else state;st=states/state;need((st/'source-state').read_text()=='edited',state);assert orig_src['stable_crate_id']==current['stable_crate_id']
 options=spawn_args(mount,r,st,st/'registry-home',[],Path(b['arms'][arm]['cargo']),Path(b['arms'][arm]['driver']));idx=options.index('--');opts=['--ro-bind',str(r),str(r),'--ro-bind',str(st/'target'),str(TARGET),'--ro-bind',str(st/'shared'),str(SHARED),'--ro-bind',str(st/'registry-home'),str(CARGO_HOME),'--ro-bind',str(st/'rustup'),str(P/'rustup'),'--bind',str(s),str(s),'--bind',str(s/'keep'),str(r/'retained-mixed'),'--bind',str(d),str(r/'bridge-canonical'),*source_binds(st)]
 # Resolve archives at the original ordinary compiler's search locations. Only the selected producer is replaced.
 physical_md=Path(current['metadata']);physical_rl=physical_md.with_suffix('.rlib');ref=load(rec(graph));ref['product']['mixed'][cr]['metadata']=str(physical_md);rf=d/'selected-producer.json';dump(rf,ref)
 if graph!=state:
  gm=exported(orig_src['rmeta_sha256'],'.rmeta');gl=exported(orig_src['archive']['sha256'],'.rlib');opts+=['--ro-bind',str(gm),str(physical_md),'--ro-bind',str(gl),str(physical_rl)]
 if brid is not None:opts+=['--ro-bind',str(brid),str(r/'libordinary_bridge_input.rlib')]
 items=[*options[:idx],*opts,*options[idx:],sys.executable,'-B','/home/dev-user/.cache/ohm-233-position-qualified-20261027/mixed-registry-seed-programs-20261027/bridge-status-worker.py','--root',str(r),'--action',act,'--crate',cr,'--arm',arm,'--out',str(d/'receipt'),'--binding',str(w/'runner-binding.json'),'--details',str(rf),'--flags',str(base/(state if state!='forced-C' else 'C')/'cold/receipt.json')];env=dict(os.environ,LC_ALL='C.UTF-8');run=subprocess.run(items,env=env,capture_output=True);(d/'wrapper.stdout').write_bytes(run.stdout);(d/'wrapper.stderr').write_bytes(run.stderr);q=d/'receipt';need((q/'stderr').is_file() and (q/'argv.json').is_file(),('no real compiler outcome',case,run.stderr[-550:]));err=(q/'stderr').read_text();case_row={'case':case,'action':act,'compiler_arm':arm,'driver':b['arms'][arm]['driver_sha256'],'context':state,'producer_from':graph,'crate':cr,'producer_full_svh':orig_src['private_svh'],'producer_rmeta_sha':orig_src['rmeta_sha256'],'producer_archive_sha':orig_src['archive']['sha256'],'bridge_input':sha(brid) if brid else None,'status':run.returncode,'codes':sorted(set(re.findall(r'error\[(E\d+)\]',err))),'stderr':err,'argv':load(q/'argv.json'),'argv_sha':sha(q/'argv.json')};success=(q/'bridge.json').is_file();need(success==(run.returncode==0),case);case_row['runtime']=load(q/'bridge.json')['runtime'] if success else None;execs.append(case_row);dump(s/'all-readers.json',execs);print(case,case_row['codes'],case_row['runtime'],flush=True);return d/'libordinary_bridge.rlib' if act=='bridge' and success else None
with(P/'native-measure.lock').open('a') as lock:
 fcntl.flock(lock,fcntl.LOCK_EX);need(not s.exists() and (r/'failure.txt').is_file() and not any((r/n).exists() for n in ('build.csv','test.csv','statistics.json')),'study state');s.mkdir(mode=0o700);(s/'exports').mkdir();(s/'keep').mkdir();index=source_clean()
 for cr in ('ruff_wasm','ty_wasm'):
  for state in ('A','B','C','forced-C'):
   tag=state+'-'+cr;brid=cmd(tag+'-direct','bridge',cr,state,state);need(brid is not None,tag);cmd(tag+'-self','caller',cr,state,state,brid)
   if state in ('A','B'):
    cmd(tag+'-versus-independent-full-on-identical-tool','caller',cr,state,'gold-'+state,brid);cmd(tag+'-independent-full-direct','bridge',cr,state,'gold-'+state)
   if state=='B':cmd(tag+'-versus-forced-C','caller',cr,'forced-C','forced-C',brid)
   if state=='C':cmd(tag+'-versus-forced-C','caller',cr,'forced-C','forced-C',brid)
   if state=='forced-C':cmd(tag+'-versus-guarded-C','caller',cr,'C','C',brid)
 need(source_clean()==index and not any((r/n).exists() for n in ('build.csv','test.csv','statistics.json')),'source or primary changed');dump(s/'complete.json',{'rows':len(execs),'no_scored_commands':True,'immutable_primary_containers':True,'source_index_sha256':index,'old_failure_sha256':sha(r/'failure.txt')})
