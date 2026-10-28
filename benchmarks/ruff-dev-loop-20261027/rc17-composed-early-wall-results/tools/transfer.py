"""Transfer the terminal evidence in one read-only H5 command after explicit release."""
import gzip
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
from export import H5


def main(destination):
    destination=destination.resolve()
    assert destination.parent.is_dir() and not destination.exists()
    code=(HERE/'export.py').read_text()
    command=['dbox','ssh',H5,'--no-tmux','--','/usr/bin/python3','-IB','-c',code]
    # The temporary file is local and preserves any interrupted transfer. No evidence is written on H5.
    tmp=destination.with_suffix(destination.suffix+'.partial')
    with tmp.open('xb') as out:
        proc=subprocess.run(command,stdout=out,stderr=subprocess.PIPE)
    with tmp.open('rb') as stream:h=hashlib.file_digest(stream,'sha256').hexdigest()
    seal=re.findall(rb'^WALL_EXPORT_SHA256 ([0-9a-f]{64}) ([0-9]+)$',proc.stderr,re.M)
    if proc.returncode:
        raise RuntimeError('H5 export exited '+str(proc.returncode)+'; launcher stderr SHA-256 '+hashlib.sha256(proc.stderr).hexdigest()+'; local partial SHA-256 '+h)
    assert len(seal)==1 and (h,tmp.stat().st_size)==(seal[0][0].decode(),int(seal[0][1]))
    with gzip.open(tmp,'rt') as f:p=json.load(f)
    assert p['status'] in ('complete','score-failed','verify-failed','admission-failed')
    # Use an exclusive hardlink on the local filesystem so an existing packet cannot be replaced.
    destination.hardlink_to(tmp);tmp.unlink()
    print(json.dumps({'packet':destination.name,'sha256':h,'bytes':destination.stat().st_size,'terminal':p['status'],
                      'remote_terminal_receipt_sha256':hashlib.sha256(proc.stderr).hexdigest()},sort_keys=True))


if __name__=='__main__':
    if len(sys.argv)!=2:raise SystemExit('usage: transfer.py NEW_LOCAL_PACKET.json.gz')
    main(Path(sys.argv[1]))
