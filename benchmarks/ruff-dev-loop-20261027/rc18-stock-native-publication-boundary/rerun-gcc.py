"""Change only the GCC prefix specs file while keeping both real native programs and their original args fixed."""
import argparse,hashlib,json,os,shutil,subprocess
from pathlib import Path
p=argparse.ArgumentParser(description=__doc__);p.add_argument('wild',type=Path);p.add_argument('sources',type=Path);p.add_argument('output',type=Path);a=p.parse_args()
D=a.output.resolve();D.mkdir(exist_ok=False)
def sha(f):return hashlib.file_digest(f.open('rb'),'sha256').hexdigest()
def command(args):return subprocess.run(args,cwd=D,env={'PATH':'/usr/bin:/bin','LC_ALL':'C'},capture_output=True,check=True)
for n in ['late','override','bin']:(D/n).mkdir()
g=Path(shutil.which('gcc')).resolve();w=D/'bin/ld.bfd';shutil.copy2(a.wild.resolve(),w)
assert sha(w)=='0d6335808b647d499f3d74993b602e64ff0625206c809bf4913c487eea380cd5'
collect2=Path(command([g,'-print-prog-name=collect2']).stdout.decode().strip()).resolve()
for n in ['start.s','fn-41.s','fn-83.s']:shutil.copyfile(a.sources/n,D/n)
command(['as','-o','start.o','start.s'])
for value,where in [(41,'late'),(83,'override')]:
    command(['as','-o',f'obj-{value}.o',f'fn-{value}.s']);command(['ar','crs',D/where/'libauditffi.a',f'obj-{value}.o'])
arg=[str(g),'-B'+str(D/'bin')+'/','-fuse-ld=bfd','-nostdlib','-nostartfiles','-nodefaultlibs','-static','-no-pie','-Wl,--dependency-file,'+str(D/'inputs.d'),'-o',str(D/'out'),str(D/'start.o'),'-L'+str(D/'late'),'-lauditffi']
rows=[]
for name in ['before','add-gcc-specs','remove-gcc-specs']:
    specs=D/'bin/specs'
    if name=='add-gcc-specs':specs.write_text('*link:\n-L'+str(D/'override')+'\n\n')
    if name=='remove-gcc-specs':specs.unlink()
    command(arg)
    produced=(D/'inputs.d').read_text().splitlines()[0].split(': ',1)[1].split()
    detail=command([arg[0],'-###',*arg[1:]]).stderr
    values={str(Path(x).relative_to(D)):sha(Path(x)) for x in produced}
    check=subprocess.run([D/'out'],cwd=D).returncode
    producer=command(['readelf','-p','.comment',D/'out']).stdout.decode()
    assert 'Linker: Wild 0.11.0' in producer
    if rows:assert all(sha(D/x)==v for x,v in rows[0]['wild_depfile'].items())
    assert check==(83 if name=='add-gcc-specs' else 41)
    rows.append(dict(phase=name,actual=check,ELF_sha256=sha(D/'out'),wild_depfile=values,gcc_reports_new_specs=b'/bin/specs' in detail,prior_wild_inputs_unchanged=True))
r=dict(gcc=sha(g),collect2=sha(collect2),wild=sha(w),argv_sha256=hashlib.sha256(b'\0'.join(x.encode() for x in arg)).hexdigest(),user_link_args=['-fuse-ld=bfd','-nostdlib','-nostartfiles','-nodefaultlibs','-static','-no-pie','-Llate','-lauditffi'],source_of_change='bin/specs',content='*link: -L<otherwise-unsearched-override>',rows=rows)
(D/'results.json').write_text(json.dumps(r,indent=2)+'\n');print([(x['phase'],x['actual']) for x in rows])
