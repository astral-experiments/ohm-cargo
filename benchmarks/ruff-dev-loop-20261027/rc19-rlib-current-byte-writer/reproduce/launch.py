"""Set up entirely private work and mount namespaces. The writer runs without capabilities."""
from pathlib import Path
import os
import shutil
import subprocess
import sys

here=Path(__file__).resolve().parent
kind,label=sys.argv[1:]
assert kind in ('ext4','btrfs') and label.isalnum()
assert os.getuid()!=0 and shutil.disk_usage(here).free>3*2**30
folder=here/('trial-'+kind+'-'+label);folder.mkdir(mode=0o700)
m=folder/'work';m.mkdir()
(folder/'empty').mkdir()
if kind=='btrfs':
    image=folder/'private.btrfs'
    with image.open('xb') as f:f.truncate(1536*1024**2)
    subprocess.run(['/usr/sbin/mkfs.btrfs','-q','-L','ohm-archive-qa',image],check=True)
with (folder/'stdout').open('xb') as out,(folder/'stderr').open('xb') as err:
    proc=subprocess.run(['sudo','-n','unshare','--mount','--propagation','private','/bin/sh',here/'mount-study.sh',here,m,folder,kind,str(os.getuid()),str(os.getgid())],stdout=out,stderr=err)
(folder/'exit').write_text(str(proc.returncode)+'\n')
if proc.returncode:
    print((folder/'stderr').read_text()[-4500:],file=sys.stderr)
sys.exit(proc.returncode)

