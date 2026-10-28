"""Probe exactly three GCC/rustc volatile operand roles, including an activated native LTO plugin."""
import json,hashlib,os,shutil,subprocess,sys
from pathlib import Path
H=lambda b:hashlib.sha256(b).hexdigest()
F=lambda p:H(Path(p).read_bytes())
wild=Path(sys.argv[1]).resolve()
root=Path(sys.argv[2]).resolve();root.mkdir();os.chdir(root)
stock='0d6335808b647d499f3d74993b602e64ff0625206c809bf4913c487eea380cd5';assert F(wild)==stock
src=Path(__file__).resolve().parent
for n in ('start','ordinary','eight'):
 subprocess.run(['as',str(src/(n+'.s')),'-o',n+'.o'],check=True)
private=root/'gcc-ld';private.mkdir()
proxy=private/'ld.bfd'
proxy.write_text('''#!/usr/bin/python3
import json,os,sys
from pathlib import Path
a=sys.argv[1:]
i,= [i for i,s in enumerate(a) if s.startswith('-plugin-opt=-fresolution=')]
before=a[i]
a[i]='-plugin-opt=-fresolution='+os.environ['LAB_RES']
Path(os.environ['LAB_ARGV']).write_text(json.dumps([before,a]))
os.execv(os.environ['LAB_STOCK'],[os.environ['LAB_STOCK'],*a])
''')
proxy.chmod(0o755)
# Neither private dir is a substitute for a user input in production: both have distinct immutable test contents.
for s in ('A','B'):
 d=root/('rustc'+s);d.mkdir();(d/'raw-dylibs').mkdir()
 shutil.copyfile('ordinary.o',d/'symbols.o')
def r(a,env=None):
 return subprocess.run(a,env=env,capture_output=True,timeout=15)
res={'input_files':{p.name:F(p) for p in map(Path,['start.o','ordinary.o','eight.o'])},'wild':stock,'cases':{}}
for s in ('A','B'):
 d=root/('rustc'+s);argv=[str(wild),'--threads=4','--build-id','--gc-sections','-e','_start','-o','image','start.o',str(d/'symbols.o'),'eight.o','-L'+str(d/'raw-dylibs')]
 cp=r(argv);assert cp.returncode==0;ret=r([str(root/'image')]).returncode;assert ret==42
 res['cases']['spelling-'+s]=dict(status=0,image=F('image'),program=ret,argv=[a.replace(str(root),'<case>') for a in argv[1:]],symbols=F(d/'symbols.o'),raw=sorted(os.listdir(d/'raw-dylibs')))
assert res['cases']['spelling-A']['image']==res['cases']['spelling-B']['image']
Path('macro.c').write_text('int main(void) { return 41; }\n')
for flavor in ('fresh-native','gcc-lto'):
 flags=['-flto','-frandom-seed=fixed'] if flavor=='gcc-lto' else []
 r(['/usr/bin/cc',*flags,'-c','macro.c','-o','macro.o']).check_returncode()
 srcsha=F('macro.o');headers=r(['/usr/bin/readelf','-WS','macro.o']).stdout
 ir_visible=b'.gnu.lto_' in headers
 assert ir_visible==(flavor=='gcc-lto')
 for name,choice in [('first',root/'first.res'),('second',root/'second.res'),('unwritable',Path('/proc/no-ohm-link-fixture/resolution.res'))]:
    Path('image').unlink(missing_ok=True)
    if choice.parent==root:choice.write_bytes(b'')
    env={'PATH':'/usr/bin:/bin','LC_ALL':'C','LAB_RES':str(choice),'LAB_ARGV':str(root/'invocation'),'LAB_STOCK':str(wild)}
    argv=['/usr/bin/cc',*flags,'-B'+str(private),'-fuse-ld=bfd','-Wl,--build-id','macro.o','-o','image']
    cp=r(argv,env)
    if Path('invocation').is_file():old,actual=json.loads(Path('invocation').read_bytes())
    else:raise RuntimeError(cp.stderr.decode())
    rows=dict(status=cp.returncode,source=srcsha,native_lto_section=ir_visible,original_arg=old.replace(str(root),'<case>'),
         actual_argv=[a.replace(str(root),'<case>') for a in actual],stdout=cp.stdout.decode().replace(str(root),'<case>'),
         stderr=cp.stderr.decode().replace(str(root),'<case>'),resolver_size=choice.stat().st_size if choice.is_file() else None)
    if Path('image').is_file():rows.update(program=r([str(root/'image')]).returncode,image=F('image'))
    rows['created_image']=Path('image').is_file()
    res['cases'][flavor+'-'+name]=rows
    print(flavor,name,rows['status'],rows.get('program'),rows['resolver_size'],rows['stderr'][:280])
(root/'result.json').write_text(json.dumps(res,sort_keys=True,indent=2)+'\n')
