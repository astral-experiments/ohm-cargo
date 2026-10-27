from pathlib import Path
import hashlib,json,os,subprocess
p=Path(__file__).resolve().parent;d=p.parent
o=p/'seed-audit';o.mkdir()
receipt=json.loads((d/'closure/reversed/receipt.json').read_bytes())
observed={}
for f in (p/'whole-pilot-v1/qualify/trace-1-selected/logs').iterdir():
 _,name=f.name.split('-',1);v=f.read_text().split();observed[name]=v[-1]
def sha(x):
 with x.open('rb') as ff:return hashlib.file_digest(ff,'sha256').hexdigest()
keys=[]
for name,s in receipt['commands'].items():
 rw=Path(s['saved']);cp=rw.parent
 for tag,which in [('none',[]),('libc',['libc']),('libm',['libm']),('both',['libc','libm'])]:
  direct=o/name/tag;direct.mkdir(parents=True);train=direct/'train';train.mkdir();trace=direct/'markers';trace.mkdir()
  orig=[Path('/usr/lib/x86_64-linux-gnu/'+lib+'.so') for lib in which]
  rules=[el for f in orig for el in ['--ro-bind',str(f),str(cp/str(f)[1:])]]
  width=3 if name.startswith('ruff_python_parser') else 5
  e=dict(os.environ,OUT=str(direct/name),OHM_DEDENT_PILOT_ROOT=str(train),OHM_DEDENT_PILOT_MODE='train',OHM_DEDENT_PILOT_TRACE=str(trace))
  cmd=['bwrap','--die-with-parent','--ro-bind','/','/','--dev-bind','/dev','/dev','--proc','/proc','--tmpfs','/tmp','--bind',str(o),str(o),*rules,'--',str(rw),str(p/'target/release/wild'),'--',f'--threads={width}','--dynamic-linker','/lib64/ld-linux-x86-64.so.2']
  r=subprocess.run(cmd,env=e,capture_output=True);(direct/'stdout').write_bytes(r.stdout);(direct/'stderr').write_bytes(r.stderr);assert r.returncode==0,(cmd,r.stderr)
  marker,=trace.iterdir();val=marker.read_text().split()[-1]
  actual=sha(direct/name);assert actual==receipt['actual'][name]['actual_elf_sha256']
  row={'name':name,'tag':tag,'matched_live':val==observed[name],'actual':val,'live':observed[name],'elf':actual,'width':width,'rebound':[{'logical':str(f),'original':sha(f),'archived':sha(cp/str(f)[1:])} for f in orig]};keys.append(row)
  print(name,tag,val,row['matched_live'],flush=True)
  (direct/name).unlink() # private disposable copy, original preserved in snapshot
(o/'result.json').write_text(json.dumps(keys,indent=2)+'\n')
