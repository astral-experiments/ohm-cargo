"""Repeat the registered profile edit on an existing, private, hydrated Ruff workspace."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import time

def sha(data):
    return hashlib.sha256(data).hexdigest()

def file_hash(path):
    with path.open('rb') as src:
        return hashlib.file_digest(src, 'sha256').hexdigest()

def safe_alarm(signum, frame):
    raise TimeoutError('Cargo exceeded the external 120-second watchdog')

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',type=Path,required=True,help='Disjoint, writable Ruff checkout at the registered commit')
    parser.add_argument('--records',type=Path,required=True,help='New empty output directory outside the checkout')
    parser.add_argument('--arm',choices=['A','B'],required=True,help='The installed +ohm Cargo under validation')
    args=parser.parse_args()
    assert os.getenv('CARGO_TARGET_DIR') and os.getenv('CARGO_BUILD_BUILD_DIR') and os.getenv('CARGO_HOME') and os.getenv('RUSTUP_HOME')
    target=Path(os.environ['CARGO_TARGET_DIR']).resolve();shared=Path(os.environ['CARGO_BUILD_BUILD_DIR']).resolve()
    source=args.source.resolve();records=args.records.resolve();assert not records.exists() and records!=source and not records.is_relative_to(source)
    assert target!=shared and not shared.is_relative_to(target) and not target.is_relative_to(shared)
    records.mkdir(parents=True,mode=0o700)
    reg=json.loads((Path(__file__).resolve().parent.parent/'blocking/registration.json').read_bytes())
    assert subprocess.check_output(['git','-C',source,'rev-parse','HEAD'],text=True).strip()==reg['Ruff']
    proxy=Path(subprocess.check_output(['rustup','which','--toolchain','ohm','cargo'],text=True).strip());assert file_hash(proxy)==reg['images'][args.arm],proxy
    assert all(x not in os.environ for x in ('RUSTC_WRAPPER','RUSTFLAGS','CARGO_ENCODED_RUSTFLAGS','LD_PRELOAD'))
    root=source/'Cargo.toml';lock=source/'Cargo.lock';start=root.read_bytes()
    addition=b'debug = "line-tables-only"\n# Avoid the local ThinLTO that Cargo enables at nonzero optimization levels.\nlto = "off"\n'
    hdr=b'[profile.fast-test]\ninherits = "dev"\nopt-level = 1\n'
    assert sha(start)==reg['root_manifest']['H'] and start.count(hdr+addition)==1 and file_hash(lock)==reg['Cargo_lock_sha256']
    reverse=start.replace(hdr+addition,hdr);assert sha(reverse)==reg['root_manifest']['P']
    command=reg['command'];previous=signal.signal(signal.SIGALRM,safe_alarm);baseline=None
    try:
        for step,manifest in (('baseline',start),('reverse',reverse),('reverse-hit',reverse),('restore',start),('restore-hit',start)):
            if root.read_bytes()!=manifest:root.write_bytes(manifest)
            assert file_hash(lock)==reg['Cargo_lock_sha256']
            # A genuine unchanged warm command is mandatory; partial hydration is a new workload.
            # Typed checks run only before the first edit and after each edit/hit pair.
            def typed():
                raw=subprocess.check_output([*command,'--message-format=json'],cwd=source)
                (records/(step+'.jsonl')).write_bytes(raw)
                allrows=[json.loads(l) for l in raw.splitlines()];ars=[r for r in allrows if r.get('reason')=='compiler-artifact']
                assert allrows[-1]=={'reason':'build-finished','success':True} and len(ars)==147 and all(r['fresh'] for r in ars)
                files={str(Path(k).relative_to(target)):file_hash(Path(k)) for r in ars for k in r['filenames'] if Path(k).is_file()}
                assert len(files)==265
                return files
            if step=='baseline':
                baseline=typed();(records/'all-265.json').write_text(json.dumps(baseline,sort_keys=True,indent=2)+'\n');continue
            with (records/(step+'.stdout')).open('xb') as out,(records/(step+'.stderr')).open('xb') as err:
                child=None
                try:
                    signal.setitimer(signal.ITIMER_REAL,120)
                    t0=time.perf_counter_ns();child=subprocess.Popen(command,cwd=source,stdout=out,stderr=err);code=child.wait();t1=time.perf_counter_ns()
                except BaseException:
                    if child is not None:child.kill();child.wait()
                    raise
                finally:signal.setitimer(signal.ITIMER_REAL,0)
            assert code==0
            if step.endswith("-hit"):assert baseline==typed()
            (records/(step+'.clock.json')).write_text(json.dumps({'origin':'new independent user replay','phase':step,'ns':t1-t0,'start':t0,'end':t1,'cargo':file_hash(proxy),'manifest':sha(manifest)},sort_keys=True)+'\n')
    finally:
        if root.read_bytes() in (start,reverse) and root.read_bytes()!=start:root.write_bytes(start)
        signal.signal(signal.SIGALRM,previous)

if __name__=='__main__':main()
