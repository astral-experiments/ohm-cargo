from pathlib import Path
import hashlib,json,os,shutil,subprocess
p=Path(__file__).resolve().parent
d=p.parent;gold=p/'native-oracles';gold.mkdir();q=p/'qualification';q.mkdir();image=p/'target/release/wild'
sha=lambda f:hashlib.file_digest(f.open('rb'),'sha256').hexdigest()
rows=json.loads((d/'closure/reversed/receipt.json').read_bytes())
alt='ff1cdc736d8eaf6dc261d3a8007b2b2fc1c046e875a73bca84eb94a2410b93a2'
records=[]
for name in sorted(rows['commands']):
 orig=d/'products/reversed'/name
 assert sha(orig)==rows['actual'][name]['actual_elf_sha256']
 for cat in ('one','multi'):
  actual=orig
  if name.startswith('ruff_python_parser-') and cat=='one':
   actual=d/'image'/Path(rows['actual'][name]['path']).relative_to('/mnt/devbox-scratch/dev-user/ohm-dedent-lane-20261027-v1')
   assert sha(actual)==alt
  blob=gold/(name+'.'+cat);shutil.copyfile(actual,blob)
  digest=subprocess.check_output([str(p/'gold-b3'),str(blob)]);assert len(digest.strip())==64
  blob.with_name(blob.name+'.blake3').write_bytes(digest)
for state,mode in [('reversed','train'),('restored','selected'),('restored','full'),('reversed','oracle')]:
 for rw in sorted((d/'closure'/state/'saved').glob('*/run-with')):
  name=Path(rw.read_text().split('# Original output file: ')[-1].strip()).name
  assert name in rows['commands']
  for width in range(1,9):
   label=f'{state}-{mode}-{name}-{width}';f=q/label;f.mkdir();out=f/name;trace=f/'trace';trace.mkdir()
   e=dict(os.environ,OUT=str(out),OHM_DEDENT_PILOT_ROOT=str(gold),OHM_DEDENT_PILOT_MODE=mode,OHM_DEDENT_PILOT_TRACE=str(trace))
   cmd=[str(rw),str(image),'--',f'--threads={width}','--dynamic-linker','/lib64/ld-linux-x86-64.so.2']
   z=subprocess.run(cmd,env=e,capture_output=True)
   (f/'stdout').write_bytes(z.stdout);(f/'stderr').write_bytes(z.stderr)
   assert z.returncode==0,(label,z.stderr)
   log,=trace.iterdir();v=log.read_text().split()
   assert int(v[0])==width and v[1]==mode and (v[2]=='true')==(mode in ('selected','oracle')),(label,v)
   expect=sha(gold/(name+('.one' if width==1 else '.multi')))
   actual=sha(out);assert actual==expect,(label,actual,expect)
   records.append({'name':name,'source':state,'rustc_native_width':width,'mode':mode,'exec':sha(image),'expected':expect,'actual':actual,'trace':v})
   out.unlink() # our transient output, digest sealed; evidence gold and original are retained
  print(state,mode,name,'all 8 exact',flush=True)
(q/'complete.json').write_text(json.dumps(records,indent=2)+'\n')
