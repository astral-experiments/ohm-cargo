"""Train a genuine cfg-disabled test, then exercise ordinary nested native script lookup."""
from pathlib import Path
import hashlib, os, socket, sys
q=Path('/dev/shm/ohm-stdlib-native-scout-20261027')
data=(q/'tiny-guards-233a9.py').read_text()
assert hashlib.sha256(data.encode()).hexdigest()=='86850093592ae28f0430e2b44bb0c46a37964d5be1a9e8d8ccbbb3aac38c4198'
assert socket.gethostname()=='charlie-ohm-relink-perf-1024'
g=data.split("base=arm.startswith(")[0]
def replace(s,old,new):
    assert s.count(old)==1
    return s.replace(old,new)
g=replace(g,"def run(label,*,","def run(label,*,bindfiles=(),")
g=replace(g," with (p/'stdout').open",""" i=cmd.index('--chdir')
 for real,dest in bindfiles:cmd[i:i]=['--ro-bind',str(real),str(dest)]
 with (p/'stdout').open""")
g=replace(g,"assert (rc!=0)==fail,","assert fail is None or (rc!=0)==fail,")
exec(compile(g,'tiny-guards-233a9-frozen','exec'))
assert arm in ('baseline-nested-root-v1','a9b-nested-root-v1','a9c-nested-root-v1')
expected={'baseline':'dd5cab154b8dcd09ccc2753160d314cade80979b2d055ee66aa9e2217e05e7e1','a9b':'991d983a45416c63bc637511ccc584ea2ca6486d1a0b190108577ef00770768f','a9c':'5227d7a8222366077a451f8d08d6e267108e16708db0326275fce212a180cf76'}
which=arm.split('-')[0]
assert sha(car)==expected[which] and sha(driver)=='dec72d1e68fdb0f8ff91fc98e8a826bf837878eca30b1ec5ea2f3258b6b2f99f'
put('Cargo.toml','[workspace]\nmembers=["kit","mark","leaf"]\nresolver="2"\n')
m=src/'kit/Cargo.toml';m.write_text(m.read_text().replace('[dev-dependencies]','[dev-dependencies]\nleaf={path="../leaf"}'))
put('leaf/Cargo.toml','[package]\nname="leaf"\nversion="0.1.0"\nedition="2024"\n')
num=0
def change():
    global num
    num+=1;put('leaf/src/lib.rs',f'pub fn n()->u32 {{ {num} }}\n')
    return num
def run_phase(name,fail=False):
    change()
    return run(name,bindfiles=binds,fail=fail)
sys_lib=Path('/usr/lib/x86_64-linux-gnu')
libutil=sys_lib/'libutil.a';librt=sys_lib/'librt.a';assert libutil.read_bytes()==librt.read_bytes()==b'!<arch>\n'
private=work/'private-sdk';sdkrel=Path('lib/rustlib/x86_64-unknown-linux-gnu/lib')
sp.run(['cp','-a','--reflink=auto','--',release/sdkrel,private],check=True)
private.chmod(private.stat().st_mode|0o200)
place=private/'x86_64-linux-gnu'
assert not place.exists();place.mkdir()
script=work/'unchanged-system-script'
script.write_text('INPUT ( x86_64-linux-gnu/librt.a )\n')
marker=work/'marker.s';marker.write_text('.globl ohm_nested_input_marker\n.set ohm_nested_input_marker, 0x97\n.section .note.GNU-stack,"",@progbits\n')
obj=work/'marker.o'
sp.run(['as','--64','-o',str(obj),str(marker)],check=True)
binds=[(private,v/sdkrel),(script,libutil)]
initial=run_phase('cold',fail=None)
if initial['rc']:
    print('cold failed',initial['messages']);sys.exit(2)
assert '0 tests' in initial['tests'] and initial['api_modes']==['full']
samples={}
def keep(name,r):
    evidence={'rc':r['rc'],'elf':r.get('elf'),'wild':r['wild'],'full':r['api_modes'],'fixed':r['fixed'],'rustcs':r['rustcs'],'tests':r.get('tests'),'diagnostics':r['messages']}
    if r.get('elf'):
        es=[p for p in (work/'target').rglob('api-*') if p.is_file() and '.' not in p.name];assert len(es)==1
        evidence['marker']=[s.split()[0] for s in sp.check_output(['nm','-a',es[0]],text=True).splitlines() if s.endswith(' ohm_nested_input_marker')]
    proof=r.get('proof')
    if proof:
        evidence['proof']={k:proof[k] for k in ('source','input_digest','fixed_worker','elf')}
        evidence['recorded_rt_order']=[s for s in proof['files'] if s.endswith('librt.a') or s.endswith('libutil.a')]
        evidence['watched_directories']=proof['directories']
    samples[name]=evidence
keep('cold',initial)
train=run_phase('first-changed');keep('first-changed',train)
steady=run_phase('ordinary-or-reuse');keep('ordinary-or-reuse',steady)
if which=='a9c':assert steady['proof']['fixed_worker'] and not steady['api_modes']
elif which=='a9b':assert steady['proof']['fixed_worker'] and steady['api_modes']==['full']
else:assert steady['api_modes']==['full']
candidate=place/'librt.a'
# An ordinary assembler object is a valid unconditionally selected ELF input even under this suffix.
candidate.write_bytes(obj.read_bytes())
r=run_phase('earlier-member-now-exists',fail=None);keep('earlier-member-now-exists',r)
candidate.write_text('INPUT ( /__ohm_nested_input_no_such_file__.o )\n')
r=run_phase('earlier-member-now-invalid',fail=None);keep('earlier-member-now-invalid',r)
candidate.unlink()
r=run_phase('removed-earlier-member',fail=None);keep('removed-earlier-member',r)
assert sha(script)==hashlib.sha256(b'INPUT ( x86_64-linux-gnu/librt.a )\n').hexdigest() and librt.read_bytes()==b'!<arch>\n'
(work/'result.json').write_text(json.dumps({'arm':which,'cargo':sha(car),'rust':sha(driver),'wild':sha(release/'lib/rustlib/x86_64-unknown-linux-gnu/bin/wild-ld/ld.bfd'),'system_script_sha':sha(script),'ordinary_fallback_sha':sha(librt),'added_object_sha':sha(obj),'samples':samples},sort_keys=True,indent=2)+'\n')
print('checked',which,[(k,(v['rc'],v.get('marker'),v['full'])) for k,v in samples.items()],flush=True)
