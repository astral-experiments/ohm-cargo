"""Keep GCC's actual native arguments stable while changing ordinary post-link processing."""
from pathlib import Path
import hashlib,json,os,subprocess,sys
stock,root=map(lambda s: Path(s).resolve(),sys.argv[1:])
h=lambda b:hashlib.sha256(b).hexdigest()
assert h(stock.read_bytes())=='0d6335808b647d499f3d74993b602e64ff0625206c809bf4913c487eea380cd5'
root.mkdir();os.chdir(root);Path('driver-prefix').mkdir()
Path('start.s').write_text('.text\n.globl _start\n_start:\nmov $60,%eax\nmov $41,%edi\nsyscall\n')
subprocess.run(['/usr/bin/as','start.s','-o','start.o'],check=True)
driver=Path('/usr/bin/gcc').resolve();cc2=Path(subprocess.check_output([driver,'-print-prog-name=collect2'],text=True).strip()).resolve()
observer=Path('driver-prefix/ld.bfd')
observer.write_text('''#!/usr/bin/python3
import hashlib,json,os,subprocess,sys
from pathlib import Path
raw=list(sys.argv[1:]);decision='full'
if os.environ.get('LAB_AUTH_OLD') and Path('out').is_file() and hashlib.sha256(Path('out').read_bytes()).hexdigest()==os.environ['LAB_AUTH_OLD']:
 decision='fake-fresh-for-experiment';rc=0
else:
 rc=subprocess.run([os.environ['LAB_WILD'],*raw]).returncode
Path('inside.json').write_text(json.dumps({'decision':decision,'args':raw,'exit':rc,'image_at_child_exit':hashlib.sha256(Path('out').read_bytes()).hexdigest() if Path('out').is_file() else None}));sys.exit(rc)
''')
observer.chmod(0o755)
post=(root/'post.py')
post.write_text('''#!/usr/bin/python3
from pathlib import Path
import hashlib,json,sys
p=Path(sys.argv[1]);data=p.read_bytes();before=hashlib.sha256(data).hexdigest()
if sys.argv[2]=='edit':
 beforebytes=bytes.fromhex('b83c000000bf290000000f05');afterbytes=bytes.fromhex('b83c000000bf530000000f05')
 assert data.count(beforebytes)==1
 p.write_bytes(data.replace(beforebytes,afterbytes))
status=7 if sys.argv[2]=='fail' else 0
Path('outer.json').write_text(json.dumps({'in':before,'out':hashlib.sha256(p.read_bytes()).hexdigest(),'exit':status}));sys.exit(status)
''')
post.chmod(0o755);specs=root/'driver-prefix/specs'
argv=[str(driver),'-B'+str(root/'driver-prefix')+'/', '-fuse-ld=bfd','-fno-use-linker-plugin','-nostdlib','-nostartfiles','-nodefaultlibs','-static','-no-pie','-Wl,--build-id','start.o','-o','out']
rows=[];baseline=None
for kind in ['ordinary','conditional-lab-pass']:
 for mode in ['noop','edit','fail','restored']:
  for f in ['inside.json','outer.json']:Path(f).unlink(missing_ok=True)
  specs.write_text('*post_link:\n'+str(post)+' out '+mode+'\n\n')
  # Exercise the same state from a true prior stock output, independently for each row.
  if baseline:Path('out').write_bytes(baseline);Path('out').chmod(0o755)
  env={'PATH':'/bin:/usr/bin','LC_ALL':'C','LAB_WILD':str(stock)}
  if kind=='conditional-lab-pass':env['LAB_AUTH_OLD']=h(baseline)
  cp=subprocess.run(argv,env=env,capture_output=True,timeout=15)
  inn=json.loads(Path('inside.json').read_bytes());outer=json.loads(Path('outer.json').read_bytes()) if Path('outer.json').exists() else None
  canon=['-plugin-opt=-fresolution=<GCC_RES>' if v.startswith('-plugin-opt=-fresolution=') else v.replace(str(root),'<case>') for v in inn['args']]
  if baseline is None:baseline=Path('out').read_bytes()
  exists=Path('out').is_file();ret=subprocess.run([str(root/'out')]).returncode if exists else None
  assert (cp.returncode!=0)==(mode=='fail'),(mode,cp.returncode,cp.stderr)
  assert outer is not None,(mode,outer,cp.stderr)
  if not cp.returncode:assert ret==(83 if mode=='edit' else 41),(mode,ret)
  row={'arm':kind,'spec':mode,'gcc_status':cp.returncode,'wild_status':inn['exit'],'wild_choice':inn['decision'],'gcc_out':h(Path('out').read_bytes()) if exists else None,'program_exit':ret,'stock_at_child_exit':inn['image_at_child_exit'],'post':outer,'stdout':cp.stdout.decode().replace(str(root),'<case>'),'stderr':cp.stderr.decode().replace(str(root),'<case>'),'normalized_native_argv':canon,'raw_native_argv_sha256':h(b'\0'.join(os.fsencode(x) for x in inn['args'])),'spec_sha':h(specs.read_bytes()) if specs.exists() else None,'input_object':h(Path('start.o').read_bytes())}
  rows.append(row);print(kind,mode,cp.returncode,ret,inn['decision'],outer)
(root/'result.json').write_text(json.dumps({'rows':rows,'gcc':h(driver.read_bytes()),'collect2':h(cc2.read_bytes()),'wild':h(stock.read_bytes()),'source':h(Path('start.s').read_bytes())},indent=2,sort_keys=True)+'\n')
assert len({tuple(r['normalized_native_argv']) for r in rows})==1
assert len({r['raw_native_argv_sha256'] for r in rows})==1
assert len({r['stock_at_child_exit'] for r in rows})==1
