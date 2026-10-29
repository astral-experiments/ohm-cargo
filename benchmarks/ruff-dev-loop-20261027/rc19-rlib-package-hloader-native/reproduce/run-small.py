"""Run the 22 ABI, filesystem and resource-limit checks in an empty private Btrfs directory."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys

here=Path(__file__).resolve().parent
sys.path.insert(0,str(here))
from native_guards import native_suite

p=argparse.ArgumentParser()
p.add_argument('root',type=Path,help='new directory on a private Btrfs mount')
args=p.parse_args()
root=args.root.resolve()
assert os.geteuid()!=0 and str(subprocess.check_output(['findmnt','-n','-T',root.parent,'-o','FSTYPE'],text=True)).strip()=='btrfs'
root.mkdir(mode=0o700);(root/'reports').mkdir();(root/'work').mkdir();(root/'qa_writer.c').write_bytes((here/'qa_writer.c').read_bytes())
so=root/'archive_probe.so'
subprocess.run(['cc','-std=gnu11','-O2','-Wall','-Wextra','-Werror','-fPIC','-shared',here/'archive_probe.c','-o',so,'-ldl','-pthread'],check=True)
native_suite(root,root/'work',so)
print(json.loads((root/'reports/native-guards-v2.json').read_bytes())['case_count'],'native cases')
