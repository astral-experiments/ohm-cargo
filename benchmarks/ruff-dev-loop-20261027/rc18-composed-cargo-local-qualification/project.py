import hashlib, json, subprocess, sys, tempfile
from pathlib import Path
repo=Path(sys.argv[1]).resolve();out=Path(sys.argv[2])
def git(*args):return subprocess.check_output(['git','-C',str(repo),*args])
def sha(b):return hashlib.sha256(b).hexdigest()
base='9a0170863f70d9a88a8b1d1f4c4e1fded4736a9c'
heads=['857652135b','62de9a49872b6369d6246eb1c63603daf473df9a','105fe8286bef83e1ad1b62b3a2c015a6ace57ee7']
final='7181bfa6256f94da142f80fd6af09cee02ec2c78'
assert git('rev-parse','HEAD').decode().strip()==final
assert git('rev-parse',final+'^{tree}').decode().strip()=='5386201eedb3970d3cc74521f12bd644cdf33396'
names=set(git('diff','--name-only',base,final).decode().splitlines())
phases=[]
with tempfile.TemporaryDirectory(prefix='ohm-cargo-rc18-projection-') as td:
    t=Path(td)
    for n in names:
        p=t/n;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(git('show',base+':'+n))
    for h in heads:
        h=git('rev-parse',h).decode().strip()
        assert subprocess.run(['git','-C',str(repo),'merge-base','--is-ancestor',h,final]).returncode==0
        diff=git('diff','--binary',base,h,'--')
        changed=git('diff','--name-only',base,h).decode().splitlines();assert set(changed)<=names
        subprocess.run(['git','apply','--recount','--whitespace=nowarn','-'],input=diff,cwd=t,check=True)
        phases.append({'head':h,'patch_sha256':sha(diff),'paths':changed})
    expected={n:sha(git('show',final+':'+n)) for n in sorted(names)}
    assert {n:sha((t/n).read_bytes()) for n in names}==expected
    assert not git('diff','--name-status',base,final,'--',*[f':(exclude){n}' for n in names])
    out.write_text(json.dumps({'base':base,'final':final,'tree':git('rev-parse',final+'^{tree}').decode().strip(),'heads':phases,'only_changed_files':expected},indent=2,sort_keys=True)+'\n')
