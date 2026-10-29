"""Verify the portable bundle, including both clock cohorts and both calibration attempts."""
from pathlib import Path
import hashlib,json,statistics,subprocess,sys

p=Path(__file__).resolve().parent
def sha(f):
    return hashlib.sha256(f.read_bytes()).hexdigest()
for line in (p/'SHA256SUMS').read_text().splitlines():
    d,name=line.split('  ');assert sha(p/name)==d,name
c=p/'timer-calibration';summary=json.loads((c/'checked.json').read_bytes())
for group in ('first','second'):
    d=c/group;rows=json.loads((d/'rows.json').read_bytes());plan=json.loads((d/'calibration-plan.json').read_bytes());s=summary['arms'][group]
    assert len(rows)==60 and sha(d/'rows.json')==s['raw'] and sha(d/'timer.py')==plan['timer'] and sha(d/'calibration.c')==plan['child']
    for mode in ('blocking','polling'):
        requested=plan['ms'];medians=[]
        for ms in requested:
            rr=[r for r in rows if r['request_ms']==ms and r['mode']==mode];assert len(rr)==3
            assert all(r['parent_start']<r['child_start']<r['child_end']<=r['parent_end'] for r in rr)
            medians.append(statistics.median((r['parent_end']-r['parent_start'])/1e6 for r in rr))
        assert medians==s['medians_ms'][mode]
    b=s['medians_ms']['blocking'];assert all(3<=y-x<=9 for x,y in zip(b,b[1:]))
    assert all(abs(x-y)<3.5 for x,y in zip(b,requested))
    tails=sorted((r['parent_end']-r['child_end'])/1e6 for r in rows if r['mode']=='blocking')
    assert tails[28]==s['blocking_p95'] and tails[-1]==s['blocking_max']
    if group=='first':assert tails[-1]>6 and s['status']==1
    else:assert tails[-1]<6 and tails[28]<2 and s['status']==0 and ', 0, NULL)' in (d/'blocking-wait.txt').read_text()
for cohort in ('initial-quantized','blocking'):
    subprocess.run([sys.executable,'-IB',p/cohort/'verify.py'],check=True)
    assert json.loads((p/cohort/'prior-clean-variance.json').read_bytes())['ordinary_wall_commands']==0
print('Verified separate cold failure, two calibrations, both native cohorts and 256 ordinary command observations.')
