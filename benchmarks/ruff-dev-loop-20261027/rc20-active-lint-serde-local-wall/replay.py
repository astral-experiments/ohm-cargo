"""Recreate a new one-host serde lint replication from authenticated local inputs."""
from pathlib import Path
import argparse,json,os,shutil,subprocess as sp
r=argparse.ArgumentParser(description=__doc__)
for n in ('study','archive','sdk','ruff','registry','parent-cargo','candidate-cargo'):r.add_argument('--'+n,required=True,type=Path)
a=r.parse_args();here=Path(__file__).resolve().parent;p=a.study.resolve();assert os.geteuid()==1000 and Path('/').stat().st_uid==0 and not p.exists()and a.archive.is_dir() and not set(range(8,12)).difference(os.sched_getaffinity(0))
assert shutil.disk_usage(Path.home()).free>45*2**30 and shutil.disk_usage(a.archive).free>40*2**30 and a.archive.resolve()!=p
p.mkdir(mode=0o700);m=p/'mount';m.mkdir();(p/'view').mkdir()
for n in ('replay-runtime.py','source.json','source-files.json','protocol.json','mechanics.py','member_archive.py','member_archive_base.py','local_study.py','controller.py','wall.py','gates.py','analysis_lint.py','reopen.py','caller.rs'):shutil.copyfile(here/n,p/n)
# The offline registry root is a complete CARGO_HOME, including registry/src, registry/index, registry/cache and any local source mapping.
(p/'replay-config.json').write_text(json.dumps(dict(ruff=str(a.ruff.resolve()),sdk=str(a.sdk.resolve()),A=str(a.parent_cargo.resolve()),B=str(a.candidate_cargo.resolve()),registry=str(a.registry.resolve())),sort_keys=True))
shell="""set -eu
mount -t tmpfs -o size=3G,mode=0700,uid=1000,gid=1000,exec,nosuid,nodev tmpfs "$1"
exec setpriv --reuid=1000 --regid=1000 --init-groups -- env HOME="$2" USER="$3" LOGNAME="$3" LINT_STUDY="$4" LINT_ARCHIVE="$5" /usr/bin/python3 -IB "$6"
"""
cmd=['sudo','-n','unshare','--mount','--propagation','private','--','/bin/sh','-ec',shell,'private-study',m,Path.home(),os.environ['USER'],p,a.archive.resolve(),p/'replay-runtime.py']
with (p/'host.stdout').open('xb')as o,(p/'host.stderr').open('xb')as e:r=sp.run(cmd,cwd=p,stdout=o,stderr=e)
print('native and score exit',r.returncode,'receipt',p/'archived.json');raise SystemExit(r.returncode)
