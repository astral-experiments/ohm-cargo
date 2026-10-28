"""Read H5 outputs only after strict refusal. Use the H8 DWARF function definitions unchanged."""
import ast,base64,collections,concurrent.futures,fcntl,hashlib,json,os,subprocess,sys
from pathlib import Path
here=Path(__file__).resolve().parent
sys.path.insert(0,str(here.parent/'protocol-v2'))
import worker as w
import explain_native as native
source=(here/'dwarf_fields.py').read_bytes()
assert hashlib.sha256(source).hexdigest()=='7468aaf4086c0d8757e1a0c7e3d6909f0527e7a667e336a9dea21f8d37c09698'
assert w.sha(here/'explain_native.py')=='384fe4c46b02ef55af02894ad42ad3e6fa7e97dd636649adba3daa18ba3ea1c7'
tree=ast.parse(source);body=[n for n in tree.body if isinstance(n,(ast.Import,ast.ImportFrom))or (isinstance(n,ast.FunctionDef)and n.name=='inspect')or (isinstance(n,ast.Assign)and isinstance(n.targets[0],ast.Name)and n.targets[0].id in ('sha','info_str'))]
g={};exec(compile(ast.Module(body=body,type_ignores=[]),'published-H8-dwarf-fields','exec'),g)
grant=w.read(w.q/'protocol-v2/paths-grant.json');ws=grant['B'][0];assert grant['C'][0]==ws
layout={'workspace':[None,ws,grant['B'][1][3:],grant['C'][1][3:]]}
g.update(p=w.q,glob='work/ruff-target/debug/build/workspaces/'+ws+'/v2-')
report=w.read(here/'structural.json');st={k:w.alias_state(int(k[0]),k[2])/'target'for k in report['states']}
def decode(job):
 name,l,r=job
 hashes=[report['all_native_sha256'][k][name]for k in (l,r)]
 files=[st[k]/report['physical_paths'][k][name]for k in (l,r)]
 assert [w.sha(f)for f in files]==hashes
 table=native.explain(files,'workspace',layout)
 # Every diff offset, including ELF and section headers or unmapped padding, is separately classified.
 assert table['sizes'][0]==table['sizes'][1]
 debug=[g['inspect'](f,grant[k[-1]][1][3:])for k,f in zip((l,r),files)]
 scope={'.debug_info','.debug_macro','.debug_str','.note.gnu.build-id'}
 ok=(set(table['differing_bytes_by_section'])==scope
     and all(len(pos)==1 and pos[0][1]=='.debug_str'for pos in table['namespace_occurrences'])
     and debug[0]['debug_strings']==debug[1]['debug_strings']and debug[0]['debug_strings']['namespace_occurrences']==1
     and all(not debug[it][sec]['stderr_len'] for it in(0,1)for sec in('info','macro'))
     and all(debug[0][sec][f]==debug[1][sec][f] for sec in('info','macro')for f in('decoded','namespaces','str_offsets','lines'))
     and all(debug[0][sec]['lines']>10000 for sec in('info','macro')))
 return name,{'sha256':hashes,'differences':table,'decoded':debug,'same_under_literal_debug_audit':ok}
def main():
 assert not(w.q/'wall').exists()and not(w.q/'qualified.json').exists()and(here/'launch-strict_diagnostic/exit').read_text()=='0'
 with(w.p/'native-measure.lock').open('rb')as lk:
  fcntl.flock(lk,fcntl.LOCK_EX|fcntl.LOCK_NB);w.clean();w.guard()
  base=report['comparisons']['1-B..1-C'];choices=[k for k,v in base['different'].items()if not v['allowed']];assert len(choices)==4
  for name in choices:
   for arm in 'BC':assert report['all_native_sha256']['1-'+arm][name]==report['all_native_sha256']['2-'+arm][name]
  with concurrent.futures.ProcessPoolExecutor(max_workers=4)as pool:checks=dict(pool.map(decode,[(n,'1-B','1-C')for n in choices]))
  semantic={}
  for k in st:
   root=st[k];env={'PATH':'/usr/bin:/bin','LC_ALL':'C','HOME':str(here)}
   ruff=root/'debug/ruff';ty=root/'debug/ty';info={}
   for path in [ruff,ty]:
    proc=subprocess.run([path,'--version'],env=env,capture_output=True);assert proc.returncode==0 and not proc.stderr
    info[path.name+'_version']=proc.stdout.decode().strip()
   proc=subprocess.run([ruff,'format','--isolated','--no-cache','--config','format.line-ending="lf"','--stdin-filename','candidate.py','-'],env=env,input=b'x=1\r\n',capture_output=True)
   assert proc.returncode==0 and proc.stdout==b'x = 1\n';info['formatted']={'out_hex':proc.stdout.hex(),'stderr_sha256':hashlib.sha256(proc.stderr).hexdigest(),'status':proc.returncode}
   semantic[k]=info
  assert len(set(json.dumps(d,sort_keys=True)for d in semantic.values()))==1
  res={'readelf':w.sha(Path('/usr/bin/readelf')),'readelf_version':subprocess.check_output(['readelf','--version'],text=True).splitlines()[0],'h8_published_sources':[w.sha(here/x)for x in('dwarf_fields.py','explain_native.py')],'exact_namespace_anchors':grant,'results':checks,'external_cli':semantic,'scope':'After strict zero-clock refusal. Two independent histories per arm give the same four paired input bytes. No timings.'}
  w.put(here/'dwarf-debug.json',res)
  print({n:v['same_under_literal_debug_audit']for n,v in checks.items()},flush=True)
if __name__=='__main__':main()
