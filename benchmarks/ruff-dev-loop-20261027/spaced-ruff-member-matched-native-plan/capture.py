"""Count real Ruff test builds on otherwise equivalent normal and spaced output paths."""
from pathlib import Path
import ast
import collections
import hashlib
import json
import os
import re
import shutil
import socket
import stat
import subprocess
import traceback

p=Path('/mnt/devbox-scratch/dev-user/ohm-spaced-ruff-20261027')
assets=p.parent/'ohm-observer-shipping-20261027/assets';sdk=assets/'stock16-sdk'
src=Path('/home/dev-user/code/oss/ruff-spaced-inputs-20261027')
pin='93526150df078af7dd8fc4226cdcc469539d2001';c=p/'logical';out=p/'qualification-v1'
def sha(f):
    with f.open('rb') as s:return hashlib.file_digest(s,'sha256').hexdigest()
def digest(b):return hashlib.sha256(b).hexdigest()
def dump(f,z):f.write_text(json.dumps(z,sort_keys=True,indent=2)+'\n')
def cmds(root):
    counts=collections.Counter();jobs=[];links=[];images=[];data={}
    for f in sorted(root.glob('exec.*')):
        rowset=f.read_bytes().splitlines();pending=None
        for raw in rowset:
            if raw.startswith((b'execve(',b'execveat(')) and raw.endswith(b'<unfinished ...>'):
                assert pending is None;pending=raw.removesuffix(b'<unfinished ...>');continue
            if m:=re.match(rb'^<\.\.\. (execve(?:at)?) resumed>(.*)$',raw):assert pending is not None;raw=pending+m[2];pending=None
            if not raw.startswith((b'execve(',b'execveat(')) or not re.search(rb'\)\s+= 0$',raw):continue
            m=re.match(rb'execve\(("(?:[^"\\]|\\.)*"),\s*(\[.*\]),\s*(?:0x[\da-f]+|NULL)',raw);assert m
            img=ast.literal_eval(m[1].decode());args=ast.literal_eval(m[2].decode());name=Path(img).name;counts[name]+=1;images.append(img)
            if name=='rustc' and '--crate-name' in args and '--out-dir' in args and '--print=file-names' not in args:
                crate=args[args.index('--crate-name')+1]
                if crate in ('___','__'):continue
                kind='link-only' if any(v in ('link-only','-Zlink-only') for v in args) else 'full'
                jobs.append(dict(crate=crate,kind=kind,trace=f.name,source=next((a for a in args if a.endswith('.rs') and not a.startswith('-')),None),argv=digest(m[2]),binary_dep=any('binary-dep-depinfo' in a for a in args)))
                if crate=='ron':data[f.name]=args
            if name=='ld.bfd' and 'wild-ld' in Path(img).parts:
                links.append(dict(path=args[args.index('-o')+1],trace=f.name,argv=digest(m[2])))
        assert not pending
    return dict(jobs=jobs,wild=links,images=images,all_names=counts,ron_commands=data)

def proof(t):
    records=[];marker=b'ohm-foreign-span-bytes'
    for which in ('target','shared'):
        physical=t/which
        for f in physical.rglob('*.d'):
            if not stat.S_ISREG(f.lstat().st_mode):continue
            data=f.read_bytes()
            if marker not in data:continue
            fingerprints=[]
            for enc in sorted((f.parent.parent/'fingerprint').glob('dep-*')):
                if not stat.S_ISREG(enc.lstat().st_mode):continue
                b=enc.read_bytes()
                if marker not in b:continue
                fingerprints.append(dict(path=str(enc.relative_to(physical)),raw=digest(b),n=len(b),has_obs1=b[-41:-37]==b'OBS1',status=b[-33] if b[-41:-37]==b'OBS1' else None))
            # Keep the raw dep file private. Publish its verified checksum lines and marker only after review.
            records.append(dict(path=str(f.relative_to(physical)),which=which,sha256=digest(data),fingerprints=fingerprints,
                contains_escaped_space=b'\\ ' in data,checksum_lines=sum(s.startswith(b'# checksum:') for s in data.splitlines())))
    return records

def main():
    assert socket.gethostname()=='charlie-ohm-cargo5-build-1025'
    os.sched_setaffinity(0,set(range(8)))
    git=lambda *args:subprocess.check_output(['git','--no-optional-locks','-C',src,*args])
    assert git('rev-parse','HEAD').decode().strip()==pin and not git('status','--porcelain','-z')
    assert not out.exists() and not c.exists() and shutil.disk_usage(p).free>70*2**30
    assert sha(sdk/'bin/cargo')=='42e90992cec21a29956e20fd52ab952472a9dbc1dcc7a3b60c92aad101b5f568' and sha(sdk/'bin/rustc')=='b0c412a7a8010a768f00546419a0b1bcfca382d7e70191df3ae72e30ac1ef3e5'
    c.mkdir(mode=0o700);out.mkdir(mode=0o700)
    for n in ('ruff-target','ruff target','shared','cargo','home'):(c/n).mkdir(mode=0o700)
    allrows={}
    for arm,tn in [('unspaced','ruff-target'),('spaced','ruff target')]:
        t=out/arm;t.mkdir(mode=0o700);reg=t/'cargo/registry';reg.mkdir(parents=True)
        for n in ('target','shared','home'):(t/n).mkdir(mode=0o700)
        for n in ('cache','index'):subprocess.run(['cp','-a','--reflink=auto','--',str(assets/'registry'/n),str(reg/n)],check=True)
        assert not any((t/'target').iterdir()) and not any((t/'shared').iterdir())
        env=dict(HOME=str(c/'home'),USER='dev-user',PATH=str(Path.home()/'.cargo/bin')+':/usr/local/bin:/usr/bin:/bin',CARGO_HOME=str(c/'cargo'),CARGO_TARGET_DIR=str(c/tn),CARGO_BUILD_BUILD_DIR=str(c/'shared'),
            CARGO_BUILD_JOBS='4',CARGO_NET_OFFLINE='true',RUSTUP_HOME=str(p/'rustup'),RUSTUP_TOOLCHAIN='ohm',RUSTUP_AUTO_INSTALL='0',CARGO_TERM_COLOR='never',GIT_OPTIONAL_LOCKS='0',LANG='C.UTF-8',LC_ALL='C.UTF-8')
        br=['bwrap','--ro-bind','/','/','--dev','/dev','--proc','/proc','--tmpfs','/tmp']
        for physical,logical in ((t/'target',c/tn),(t/'shared',c/'shared'),(t/'home',c/'home'),(t/'cargo',c/'cargo')):br+=['--bind',str(physical),str(logical)]
        ledger=[];allrows[arm]=ledger
        for i in range(5):
            dot=t/('call-'+str(i));dot.mkdir();(dot/'trace').mkdir()
            print('Ruff ty_project tests',arm,i,flush=True)
            cmd=['cargo','+ohm','test','--no-run','-p','ty_project','--locked','--offline','-j4','--message-format=json']
            traced=['strace','-ff','-qq','-s','1048576','-e','trace=execve,execveat','-o',str(dot/'trace/exec'),*cmd]
            with (dot/'stdout').open('xb') as so,(dot/'stderr').open('xb') as se:
                rc=subprocess.run([*br,'--bind',str(dot),str(dot),'--chdir',str(src),'--',*traced],env=env,stdout=so,stderr=se,stdin=subprocess.DEVNULL).returncode
            dump(dot/'command.json',dict(status=rc,package='ty_project',cmd=cmd,target=str(c/tn),shared=str(c/'shared'),cargo=sha(sdk/'bin/cargo'),stdout=sha(dot/'stdout'),stderr=sha(dot/'stderr')))
            assert rc==0,(arm,i,rc)
            rows=[json.loads(l) for l in (dot/'stdout').read_bytes().splitlines()];assert rows[-1]=={'reason':'build-finished','success':True}
            arts=[v for v in rows if v['reason']=='compiler-artifact'];ron=[r for r in arts if r['target']['name']=='ron'];assert len(ron)==1 and any(r['target']['name']=='ty_project' and r['profile']['test'] for r in arts)
            pr=cmds(dot/'trace');dump(dot/'physical.json',pr)
            snap=proof(t);dump(dot/'proof.json',snap)
            exes={r['executable'] for r in arts if r['executable']};assert not exes.intersection(pr['images'])
            outputs={}
            for exe in exes:
                e=Path(exe);assert e.is_relative_to(c/tn);outputs[exe]=sha(t/'target'/e.relative_to(c/tn))
            ledger.append(dict(call=i,units=len(arts),dirty=[r['target']['name'] for r in arts if not r['fresh']],ron_fresh=ron[0]['fresh'],
                jobs=collections.Counter(v['kind'] for v in pr['jobs']),ron_jobs=[v for v in pr['jobs'] if v['crate']=='ron'],wild=len(pr['wild']),
                observer=[(h['path'],[(f['has_obs1'],f['status']) for f in h['fingerprints']]) for h in snap],
                native=outputs,tests_executed=0))
            assert hashlib.sha256(git('ls-files','-s','-z')).hexdigest()=='fc84f15ac7401cd9bdc362e4574c6d395529766c16be2e6b032ac47fa63d21cd'
            dump(out/'progress.json',allrows)
    assert not git('status','--porcelain','-z');dump(out/'complete.json',allrows)
    print('completed all ten untimed controls',flush=True)
if __name__=='__main__':
    try:main()
    except BaseException:
        if out.is_dir():(out/'failure.txt').write_text(traceback.format_exc())
        raise
