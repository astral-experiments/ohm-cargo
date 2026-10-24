import os
from pathlib import Path
import sys

root = Path('/home/dev-user/ohm-loader-restack-20261024')
job = Path(sys.argv[1])
assert job.parent == root / 'incoming/controls'
name = job.stem
assert name.replace('-', '').isalnum()
prefix = root / 'logs' / (name + '.owner')
# Keep the controlling PTY open in this supervisor. Child Popen(close_fds=True)
# closes this handle; every workload still uses only its owned stdio files.
keep_terminal = os.dup(0)
os.set_inheritable(keep_terminal, True)
for fd, suffix, flags in ((0, '.stdin', os.O_RDONLY), (1, '.stdout', os.O_WRONLY | os.O_CREAT | os.O_EXCL), (2, '.stderr', os.O_WRONLY | os.O_CREAT | os.O_EXCL)):
    opened = os.open(str(prefix) + suffix, flags, 0o600)
    os.dup2(opened, fd)
    if opened != fd:
        os.close(opened)
os.execv('/usr/bin/python3', ['/usr/bin/python3', '-I', '-B', str(root / 'incoming/controls/owner.py'), str(job)])
