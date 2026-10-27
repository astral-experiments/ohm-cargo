"""Unscored complete copied native closures and actual destination state on real Ruff Cargo events."""
import errno
import stat
import time
from pathlib import Path
x=Path(__file__).resolve().parent
exec(compile((x/'layout-cohort.py').read_text().split('out=private/"products"')[0],str(x/'layout-cohort.py'),'exec'))
cap=x/'closure';cap.mkdir()
# Wild's save feature tries to hard-link first. Require separate namespace mounts even for
# the two independently owned tmpfs inputs, plus physically distinct shared SDK/system inputs.
source_test=root/'link-probe';source_test.write_bytes(b'private')
try:os.link(source_test,cap/'link-probe')
except OSError as e: assert e.errno==errno.EXDEV,e
else: raise AssertionError('capture could alter external inode metadata')
source_test.unlink()
assert cap.stat().st_dev!=sdk.stat().st_dev and cap.stat().st_dev!=Path('/usr/lib').stat().st_dev
assert shutil.disk_usage(cap).free>14*2**30
sc['gate']('original')
for st in ('reversed','restored'):
    d=cap/st;d.mkdir();saved=d/'saved';saved.mkdir();ent=d/'entry';ent.mkdir()
    adjust(st)
    e=dict(env,WILD_SAVE_BASE=str(saved),WILD_WRITE_LAYOUT='1',LD_PRELOAD=str(x/'link-entry.so'),DEDENT_WILD_ENTRY=str(ent))
    row=command('test','closure-'+st,e,st,trace=True)
    ref=json.loads((x/'reference'/st/'receipt.json').read_bytes())
    assert row['processes']['jobs']==ref['processes']['jobs'] or sorted(row['processes']['jobs'])==sorted(ref['processes']['jobs'])
    assert sorted(row['processes']['wild'])==sorted(ref['processes']['wild']) and row['elf']==ref['elf'] and row['total']==148
    actual={}
    for f in ent.iterdir():
        exe,path,err,*details=f.read_text().splitlines()
        assert sha(Path(exe))==plan['wild'] and path in row['elf']
        actual[Path(path).name]={'path':path,'errno':int(err),'details':details,'actual_elf_sha256':sha(Path(path))}
    assert sorted(actual)==sorted(row['processes']['wild']),actual
    commands={}
    for rw in saved.glob('*/run-with'):
        source=rw.read_text();path=source.split('# Original output file: ')[-1].strip();assert path in row['elf'],source[-500:]
        assert Path(path).name not in commands
        commands[Path(path).name]={'saved':str(rw),'bytes':sum(y.stat().st_size for y in rw.parent.rglob('*') if not y.is_symlink() and y.is_file()),'script_sha':sha(rw)}
    assert sorted(commands)==sorted(actual),(commands,actual)
    active,=[Path(s) for s in row['artifacts'] if 'libruff_python_trivia-' in s and s.endswith('.rlib')]
    for s in saved.glob('*/**/'+active.name):
        assert s.stat().st_ino!=active.stat().st_ino and sha(s)==sha(active)
    shutil.copy2(active,d/'trivia.rlib')
    for name,pair in actual.items():
        elf=Path(pair['path']);shutil.copy2(elf.with_name(elf.name+'.layout'),d/(name+'.layout'))
    # Our original real caller used standalone rustc's default native linker. Match packaged
    # Cargo's four observed Wild routing options in this separate selection control.
    orig=json.loads((root/'records/test'/('layout-'+st)/'ordinary-0/argv.json').read_bytes())
    assert orig[-2]=='-o';orig[-1]=str(cap/'ordinary')
    flags=['-Clinker-features=-lld','-Clink-self-contained=-linker','-Clink-arg=-B'+str(sdk/'lib/rustlib/x86_64-unknown-linux-gnu/bin/wild-ld'),'-Clink-arg=-fuse-ld=bfd']
    ctl=d/'ordinary';ctl.mkdir()
    rc=subprocess.run(orig+flags,cwd=sc['W'],env=dict(env,WILD_WRITE_LAYOUT='1'),capture_output=True)
    assert rc.returncode==0,rc.stderr
    underlying=cap/'ordinary'
    native=subprocess.run([underlying],capture_output=True);assert native.returncode==0 and native.stdout.decode()==plan['oracles'][st] and not native.stderr
    shutil.copy2(cap/'ordinary.layout',ctl/'ordinary.layout');shutil.copy2(underlying,ctl/'ordinary')
    save(ctl/'receipt.json',{'argv':orig+flags,'elf':sha(underlying),'stdout':native.stdout.decode(),'layout':sha(ctl/'ordinary.layout')})
    save(d/'receipt.json',{'actual':actual,'commands':commands,'cargo':row['processes'],'total':row['total'],'dirty':row['dirty']})
    print(st,actual,commands,flush=True)
    fresh=command('test','closure-'+st+'-fresh',env,st,trace=True)
    assert not fresh['processes']['wild'] and not fresh['processes']['jobs'] and fresh['fresh']==148
save(cap/'complete.json',{'outcomes':2,'fresh':2})
