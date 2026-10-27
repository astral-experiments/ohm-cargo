"""Examine named query fingerprints in a genuine restore while its bounded generation survives."""
from pathlib import Path
import concurrent.futures,hashlib,json,os,time,traceback,sys
from scan import scan,keys
from capture import birth, observed,source, q,proto,p,out,logical,save,j,sha,wait,src,tag
root=out/'typed-queries';root.mkdir(exist_ok=True);kinds=j(root/'kinds.json')
assert os.sched_getaffinity(0)<={30,31} and len(kinds)==357
def examine(mode,arm,phase):
 call=q/'receipts'/mode/arm/(tag+'-'+phase);st=q/'state'/mode/arm;dst=root/mode/arm;dst.mkdir(parents=True,exist_ok=True)
 try:
  if phase=='edit':
   time.sleep(.3);wait(out/mode/arm/'manifest.json');mr=j(out/mode/arm/'manifest.json');rx=mr['jobs']
   bounds=mr['command_bounds_us'];h=mr['command_receipt_sha256'];snap=dict(label=tag,lexer_rs_sha256=mr['source_before']['lexer_rs_sha256'])
  else:
   wait(call/'receipt.json');r=j(call/'receipt.json');assert r['source_view']=='original';bounds=[birth(call/'stdout'),(call/'invocation.json').stat().st_mtime_ns//1000];rx=[]
   expected=j(q/'fixture/manifest.json')['original'][src];snap=dict(label=(st/'source-state').read_text(),lexer_rs_sha256=sha(st/'inputs'/src));assert snap==dict(label='original',lexer_rs_sha256=expected)
   for rec in r['processes']['jobs']:
    if rec['kind']!='full':continue
    inc,jb=observed(call,rec);base=st/'target'/inc.relative_to(logical)/jb['directory'];paths=[]
    for f in base.glob('s-*/dep-graph.bin'):
     if not f.parent.name.endswith('-working') and bounds[0]<=int(f.parent.name.split('-')[1],36)<=bounds[1]:paths.append(f)
    jb['restore_graphs']=list(map(str,paths));rx.append(jb)
   h=sha(call/'receipt.json')
  sid,=[u['stable_crate_id'] for u in rx if u['crate']=='ruff_python_parser' and not u['test']]
  oh={'phase':phase,'arm':arm,'mode':mode,'command_receipt':h,'bounds_us':bounds,'source':snap,'keys':keys(sid),'jobs':[]}
  for j0 in rx:
   sid2=j0['stable_crate_id'] if j0['crate']=='ruff_python_parser' else sid
   if phase=='edit':
    fs=[out/mode/arm/j0['trace']/f['name'] for f in j0['files'] if f['name']=='dep-graph.bin']
   else:fs=list(map(Path,j0['restore_graphs']))
   jr={k:j0[k] for k in ('crate','stable_crate_id','test','trace','exec_line_sha256','explicit_parser')}
   if len(fs)!=1:
    jr['miss']='no unique command-specific graph';oh['jobs'].append(jr);continue
   f,=fs
   try:
    before=f.stat();jr['result']=scan(root/'query-graph',f,sid2,kinds);after=f.stat();assert(before.st_ino,before.st_size,before.st_ctime_ns)==(after.st_ino,after.st_size,after.st_ctime_ns)
    jr['graph']=dict(bytes=before.st_size,session=j0['candidate_sessions'][0] if phase=='edit' else f.parent.name,mtime_ns=before.st_mtime_ns,keys=keys(sid2))
   except (OSError,AssertionError) as e:jr['miss']=repr(e)
   oh['jobs'].append(jr)
  if phase=='restore':
   fr=call.with_name(call.name+'-fresh')/'receipt.json';wait(fr);fresh=j(fr);assert fresh['source_view']=='original' and fresh['unit_count']==fresh['fresh_units'] and not fresh['processes']['jobs'];oh['fresh_receipt_sha256']=sha(fr)
  save(dst/(phase+'.json'),oh);print(mode,arm,phase,'recorded',len(oh['jobs']),flush=True);return True
 except BaseException:
  (dst/(phase+'-error.txt')).write_text(traceback.format_exc());print('failed',mode,arm,phase,traceback.format_exc(),flush=True);return False
with concurrent.futures.ThreadPoolExecutor(8) as pool:
 rows=list(pool.map(lambda z:examine(*z),[(m,a,p)for m in ('build','test')for a in 'BC' for p in ('edit','restore')]))
save(root/'complete.json',dict(success=rows))
