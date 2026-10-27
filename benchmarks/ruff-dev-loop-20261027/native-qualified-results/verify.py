"""Recompute the Ruff build and test measurements from the four recorded endpoint archives."""
from collections import Counter
import csv
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import tarfile
import tempfile

here = Path(__file__).resolve().parent
tag = 'posobs4fmt-c3'
endpoints = ['doc-build','doc-test','parser-build','parser-test']

def load(path):
    return json.loads(path.read_bytes())

def run(*args):
    return json.loads(subprocess.check_output([sys.executable,'-B',*map(str,args)]))

def verify_checksums():
    for row in (here/'SHA256SUMS').read_text().splitlines():
        digest, name = row.split('  ',1)
        path=here/name
        assert re.fullmatch(r'[0-9a-f]{64}',digest) and path.resolve().is_relative_to(here)
        with path.open('rb') as stream:
            assert hashlib.file_digest(stream,'sha256').hexdigest()==digest,name

verify_checksums()
qual=load(here/'complete.json')
assert qual['source_clean'] and load(here/'release-semantics-approved.json')['driver']==qual['candidate_driver']
check=load(here/'check/summary.json')
for arm in ('parent','candidate'):
    d=here/'check'/arm
    edit=load(d/'edit/receipt.json')
    assert edit==check[arm] and edit['units']==520
    assert edit['processes']=={'rustc_full':1} and edit['crates']==[['rustc_full','ruff_python_parser']]
    assert edit['roster_sha256']==check['parent']['roster_sha256']
    calls=load(d/'edit/physical-execs.json')
    assert [[v[2],v[3]] for v in calls]==edit['crates']
    for f in d.glob('*-fresh/receipt.json'):
        fresh=load(f)
        assert fresh['units']==520 and fresh['roster_sha256']==edit['roster_sha256'] and not fresh['dirty']
assert load(here/'linter-behavior/complete.json')['source_clean']
for mode,units in [('build',501),('test',619)]:
    d=here/'linter-behavior'/mode
    orig,edit,restored=[load(d/phase/'result.json') for phase in ('original','edited','restored')]
    assert orig['sha']==edit['sha']==restored['sha']==qual['candidate_driver']
    assert orig['source']==restored['source'] and orig['source']!=edit['source']
    assert orig['diagnostics']==restored['diagnostics']
    assert [[v['code'],v['location']['row']] for v in orig['diagnostics']]==[['RUF008',4],['RUF008',6]]
    assert [[v['code'],v['location']['row']] for v in edit['diagnostics']]==[['RUF008',6]]
    for phase,out in [('original',orig),('edited',edit),('restored',restored)]:
        fresh=load(d/phase/'fresh/receipt.json')
        assert fresh['fresh']==units and not fresh['dirty']
        if out['processes'] is not None:
            calls=load(d/phase/'physical-execs.json')
            assert Counter(v[2] for v in calls)==out['processes']
            assert sorted([[v[2],v[3]] for v in calls if v[3]])==out['crates']
with tempfile.TemporaryDirectory() as tmp:
    root=Path(tmp)
    for endpoint in endpoints:
        with tarfile.open(here/(endpoint+'.tar.gz')) as archive:
            for member in archive:
                assert member.isfile() and (root/member.name).resolve().is_relative_to(root)
                target=root/member.name
                target.parent.mkdir(exist_ok=True,parents=True)
                with target.open('xb') as dest:
                    dest.write(archive.extractfile(member).read())
        study=root/f'pairs-{tag}-{endpoint}'
        schedule=load(study/'plan.json')
        odds=load(here/'plan.json')['endpoints'][endpoint]
        for key in ('orders','control','edit','mode'):
            assert schedule[key]==odds[key]
        assert schedule['source']==load(here/'plan.json')['pin']
        for row in csv.DictReader((study/'observations.csv').read_text().splitlines()):
            item=study/f"{row['arm']}-pair-{int(row['pair']):02d}"/'receipt.json'
            assert int(row['elapsed_ns'])==load(item)['ns']
    for witness in sorted(root.rglob('physical-execs.json')):
        events=load(witness)
        for filename,line_sha,kind,crate in events:
            assert re.fullmatch(r'exec\.\d+',filename) and re.fullmatch(r'[a-f0-9]{64}',line_sha)
            assert kind in ('wild','rustc_full','rustc_link_only')
            assert (kind=='wild' and crate is None) or (isinstance(crate,str) and re.fullmatch(r'[A-Za-z0-9_]+',crate))
        observed=load(witness.with_name('receipt.json'))
        assert Counter(e[2] for e in events)==observed['processes']
        assert sorted([[k,c] for _,_,k,c in events if c])==observed['crates']
    edits=run(here/'analyze-native.py',*[root/f'pairs-{tag}-{ep}' for ep in endpoints])
    fresh=run(here/'secondary-noops.py',root,tag,here/'analyze-native.py')
    accepted=run(here/'qualify-position.py',root,tag)
    for name,value in (('timings.json',edits),('immediate-noops.json',fresh),('acceptance.json',accepted),('edit-elf-changes.json',run(here/'compare-native-edit.py',root,tag))):
        assert value==load(here/name),name
    compact=lambda rows:[{k:r[k] for k in ('endpoint','pairs','parent_median_s','candidate_median_s','geometric_elapsed_reduction_pct','paired_bootstrap_95_pct','faster_pairs','holm_p_across_submitted_endpoints')} for r in rows]
    print(json.dumps({'edits':compact(edits),'unchanged':compact(fresh)},indent=2))
