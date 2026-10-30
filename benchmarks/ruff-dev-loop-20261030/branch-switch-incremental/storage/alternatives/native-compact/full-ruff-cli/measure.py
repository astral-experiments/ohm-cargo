#!/usr/bin/env python3
"""Run the ordinary Ruff build and read its two Cargo directories on an exclusive tmpfs."""
import argparse, gzip, hashlib, importlib.util, json, os, statistics, subprocess, threading, time
from pathlib import Path

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mount',type=Path,required=True,help='dedicated Linux tmpfs containing only products/ and shared/')
    parser.add_argument('--save',type=Path,required=True,help='new output directory on a different filesystem')
    parser.add_argument('--source',type=Path,required=True,help='already checked out historical Ruff source')
    parser.add_argument('--cache',choices=['off','on'],required=True)
    opts=parser.parse_args()
    root=opts.mount.resolve(strict=True);save=opts.save.resolve();source=opts.source.resolve(strict=True)
    assert os.path.ismount(root) and root.stat().st_dev!=root.parent.stat().st_dev
    assert subprocess.check_output(['findmnt','-rn','-o','FSTYPE','-T',root],text=True).strip()=='tmpfs'
    assert {p.name for p in root.iterdir()}=={'products','shared'}
    for n in ('products','shared'):
        p=root/n;assert p.is_dir() and not p.is_symlink() and p.stat().st_dev==root.stat().st_dev
    assert not save.exists() and save.parent.resolve(strict=True).stat().st_dev!=root.stat().st_dev
    assert source.stat().st_dev!=root.stat().st_dev and (source/'Cargo.lock').is_file()
    assert not (os.environ.get('RUSTFLAGS') or os.environ.get('CARGO_ENCODED_RUSTFLAGS')),'start with no extra compiler flags'
    spec=importlib.util.spec_from_file_location('census',Path(__file__).with_name('census.py'));meter=importlib.util.module_from_spec(spec);spec.loader.exec_module(meter)
    save.mkdir(mode=0o700)
    def write(name,row):
        (save/name).write_text(json.dumps(row,sort_keys=True,indent=2)+'\n')
    before=meter.census(root/'products',root/'shared');write('before.json',before)
    data=[];stop=threading.Event();fd=os.open(root,os.O_RDONLY|os.O_DIRECTORY)
    def sample():
        fs=os.fstatvfs(fd);data.append((time.monotonic_ns(),(fs.f_blocks-fs.f_bfree)*fs.f_frsize))
    def loop():
        while not stop.wait(.010):sample()
    env={**os.environ,'CARGO_TARGET_DIR':str(root/'products'),'CARGO_BUILD_BUILD_DIR':str(root/'shared')}
    if opts.cache=='on':env['CARGO_ENCODED_RUSTFLAGS']='-Zohm-branch-cache=yes'
    worker=threading.Thread(target=loop);cmd=['cargo','+ohm','build','-p','ruff','--bin','ruff','--locked','--offline','-j4','--message-format=json']
    with (save/'cargo.stdout').open('xb') as stdout,(save/'cargo.stderr').open('xb') as stderr:
        sample();worker.start()
        try:p=subprocess.run(cmd,env=env,cwd=source,stdout=stdout,stderr=stderr)
        finally:stop.set();worker.join();sample();os.close(fd)
    after=meter.census(root/'products',root/'shared');write('after.json',after)
    raw=''.join(f'{t-data[0][0]} {n}\n' for t,n in data).encode()
    (save/'statvfs.tsv.gz').write_bytes(gzip.compress(raw,compresslevel=2,mtime=0))
    gaps=sorted(b[0]-a[0] for a,b in zip(data,data[1:]))
    report={'exit':p.returncode,'argv':cmd,'option':opts.cache,'whole_before':data[0][1],'whole_after':data[-1][1],'max_observed':max(v[1] for v in data),'nominal_interval_ns':10000000,'sample_count':len(data),'gaps_ns':{'min':min(gaps),'median':statistics.median(gaps),'p99':gaps[int(.99*(len(gaps)-1))],'max':max(gaps)},'sample_tsv_sha256':hashlib.sha256(raw).hexdigest()}
    write('command.json',report)
    assert before['all']['allocated_bytes']==data[0][1] and after['all']['allocated_bytes']==data[-1][1],'other writers or unaccounted allocated blocks'
    print(json.dumps(report));return p.returncode
if __name__=='__main__':raise SystemExit(main())
