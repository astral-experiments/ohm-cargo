"""Build trusted namespace ancestors while preserving the benchmark's exact logical source and runtime paths."""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parent))
import os,shutil,stat
from common import P,CARGO_HOME,TARGET,SHARED,FROZEN,SONAME,need

def skeleton(where):
    root=where/'secure-root';root.mkdir(mode=0o700); branches=set(CARGO_HOME.parents); mounts=[]
    def populate(orig,dest):
        for src in sorted(orig.iterdir()):
            out=dest/src.name;mode=src.lstat().st_mode
            if stat.S_ISLNK(mode):out.symlink_to(os.readlink(src));continue
            if stat.S_ISDIR(mode):out.mkdir(mode=0o700)
            elif stat.S_ISREG(mode):out.touch()
            else:continue
            if src==root:continue
            if src in branches:populate(src,out)
            elif src==Path('/proc'):mounts.extend(['--proc','/proc'])
            elif src==Path('/dev'):mounts.extend(['--dev-bind','/dev','/dev'])
            elif src==Path('/tmp'):mounts.extend(['--bind','/tmp','/tmp'])
            elif src in {CARGO_HOME,TARGET,SHARED}: pass
            else:mounts.extend(['--ro-bind',str(src),str(src)])
    populate(Path('/'),root)
    return ['bwrap','--ro-bind',str(root),'/',*mounts]

def cargo_home(where,original):
    where.mkdir(mode=0o700); extras=[]
    for p in original.iterdir():
        out=where/p.name
        if p.name in {'registry','git'} and p.resolve().is_dir():
            out.mkdir(mode=0o700);extras.append((p.resolve(),CARGO_HOME/p.name));continue
        if p.is_dir():shutil.copytree(p,out,symlinks=True)
        elif p.is_file():shutil.copy2(p,out)
    need((where/'registry').is_dir(),'offline registry absent');return extras

def spawn_args(base,where,st,home,extra,cargo,driver):
    opts=[*base,'--bind',str(where),str(where),'--bind',str(P/'rustup'),str(P/'rustup')]
    for src,dst in [(st/'target',TARGET),(st/'shared',SHARED),(home,CARGO_HOME),*extra]:opts+=['--bind',str(src),str(dst)]
    for src,dst in [(cargo,FROZEN/'bin/cargo'),(driver,FROZEN/'lib'/SONAME)]:opts+=['--ro-bind',str(src),str(dst)]
    return [*opts,'--','taskset','-c','0-23']
