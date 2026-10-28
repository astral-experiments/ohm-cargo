"""Build the portable result archive after all registered work or material rejection."""
import hashlib,json,subprocess,sys,zipfile
from pathlib import Path
root=Path(__file__).resolve().parent;work=root.parent
summary=json.loads((root/'summary.json').read_text());states=[x['state'] for x in summary['cohorts'].values()]
assert any(s=='rejected' for s in states) or all(s in ('qualified','inconclusive') for s in states),states
subprocess.run([sys.executable,'-I','-S',str(root/'report.py')],check=True)
include=['RESULTS.md','report.py','plan.json','registered.sha256','registration.md','reproduce.md','host.json','staged-binaries.json','native-trace-preflight.log','register.py','common.py','run.py','summarize.py','run-local.py','verify.py','package.py','archive-check.py','finish.sh','driver.log','summary.json','portable-summary.json','calibration.log']
keep={root/x for x in include if (root/x).is_file()}
for folder in [root/'calibration',root/'attempt-0-prewarm-exdev',root/'attempt-1-premeasurement-ptrace']:
    keep.update(f for f in folder.rglob('*') if f.is_file())
for which in ('initial','replica'):
    phase=root/which
    if not phase.is_dir():continue
    keep.update(f for f in phase.iterdir() if f.is_file())
    for sub in phase.iterdir():
        if not sub.is_dir():continue
        if sub.name.startswith(('admission-','samples-')):
            keep.update(f for f in sub.iterdir() if f.is_file() and (f.suffix=='.json' or f.name=='cargo.log' or f.name.startswith('exec.')))
        elif (sub/'cargo.log').is_file():keep.add(sub/'cargo.log')
deps=['tree-count/README.md','tree-count/reproduce.md','tree-count/calibrate.c','tree-count/calibrate.py','tree-count/calibration/PASS.json','tree-count/wrap.py','tree-count/identical.py','measure.py','edit_holdout.py','edit-link-profile/native-instrument/count.py','pgo-confirmation-v2/provenance.json','pgo-confirmation-v2/audit.json','pgo-confirmation-v2/summary-base.txt','pgo-confirmation-v2/summary-guard-stack.txt','edit-holdout-cumulative-wall/test/protocol.json','pgo-holdout/README.md','pgo-holdout/run.py','pgo-holdout/provision.py','pgo-holdout/audit.py','path-compare/std-path-mismatch-guarded.patch','wild-prefix-v2/README.md','wild-prefix-v2/candidate.patch','wild-prefix-v2/regression-test.patch']
out=root/'evidence.zip'
with zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED,compresslevel=3) as z:
    for path in sorted(keep):z.write(path,path.relative_to(root))
    for rel in deps:z.write(work/rel,'dependencies/'+rel)
    for name in ['wild-link-benchmarks.zip','ohm-wild-undefined-symbols.patch']:z.write(work.parent/'outputs'/name,'dependencies/'+name)
    names=set(z.namelist());assert len(names)==len(z.namelist()) and 'verify.py' in names
with zipfile.ZipFile(out) as z:assert z.testzip() is None
with out.open('rb') as f:s=hashlib.file_digest(f,'sha256').hexdigest()
print(out,len(names),out.stat().st_size,s)
