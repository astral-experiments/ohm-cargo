"""Analyze the two registered immediate no-op controls using the same balanced randomization test."""
import csv, json, subprocess, sys, tempfile
from pathlib import Path

root=Path(sys.argv[1]).resolve()
tag=sys.argv[2]
script=Path(sys.argv[3]).resolve()
with tempfile.TemporaryDirectory() as tmp:
    reports=[]
    for ep in ('doc-build','doc-test'):
        measured=root/f'pairs-{tag}-{ep}'
        dst=Path(tmp)/('immediate-noop-'+ep);dst.mkdir();reports.append(dst)
        for name in ('plan.json','complete.json'):(dst/name).symlink_to(measured/name)
        with (measured/'observations.csv').open() as source,(dst/'observations.csv').open('w',newline='') as out:
            rows=csv.DictReader(source);writer=csv.DictWriter(out,fieldnames=rows.fieldnames);writer.writeheader()
            for row in rows:
                i=int(row['pair']);arm=row['arm'];current=measured/f'{arm}-noop-{i:02}/receipt.json'
                row['elapsed_ns']=json.loads(current.read_bytes())['ns'];writer.writerow(row)
                name=f'{arm}-pair-{i:02}-edit-fresh';(dst/name).symlink_to(measured/name, target_is_directory=True)
        for arm in ('parent','candidate'):
            for dst_name,src_name in [('verify-edit','verify-noop'),('verify-final-edit','final-noop')]:
                rowdir=measured/f'{arm}-{src_name}'
                witness=json.loads((rowdir/'receipt.json').read_bytes())
                assert not witness['dirty'] and not any(witness['processes'].values())
                (dst/f'{arm}-{dst_name}').symlink_to(rowdir,target_is_directory=True)
    result=subprocess.run([sys.executable,script,*reports],check=True,capture_output=True)
    print(json.dumps(json.loads(result.stdout),indent=2))
