"""Stage identical binary bytes when the sandbox separates the archive and fixture mounts."""
import os,shutil,signal,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
import run
from common import ARMS,HERE,SLOTS,digest,jread,save
def main():
    d=SLOTS.with_name(SLOTS.name+'-executables');d.mkdir(mode=0o700)
    pins=jread(HERE/'plan.json')['arm_hashes'];arms={};audit={}
    for arm,paths in ARMS.items():
        copied=[];audit[arm]={}
        for role,path in zip(['cargo','wild'],paths):
            q=d/f'{arm}-{role}';shutil.copy2(path,q)
            assert digest(path)==digest(q)==pins[arm][role]
            test=q.with_suffix('.check-link');os.link(q,test);assert q.samefile(test);test.unlink()
            copied.append(q);audit[arm][role]={'original':str(path),'same_mount_copy':str(q),'sha256':digest(q)}
        arms[arm]=tuple(copied)
    save(HERE/'staged-binaries.json',audit)
    # Counter-visible cargo/wild paths remain the registered paths. Only the source
    # in the selector's outside-measurement hardlink operation is relocated.
    run.ARMS=arms
    run.main()
if __name__=='__main__':
    signal.signal(signal.SIGTERM,lambda a,b:(_ for _ in ()).throw(KeyboardInterrupt()))
    try:main()
    finally:run.summarize()
