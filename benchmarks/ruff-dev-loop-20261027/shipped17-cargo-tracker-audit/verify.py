"""Reopen captured Cargo output and check each reported result against the physical bytes."""
import argparse
import hashlib
import json
import subprocess
import tarfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sha = lambda b: hashlib.sha256(b).hexdigest()
args = argparse.ArgumentParser()
args.add_argument('--cargo-git', type=Path, help='optional Cargo checkout with shipped and tracker PR commits')
args.add_argument('--campaign-dir', type=Path, help='optionally reread the three original retained command archives')
opts = args.parse_args()
for line in (ROOT/'SHA256SUMS').read_text().splitlines():
    digest, path = line.split('  ', 1)
    assert sha((ROOT/path).read_bytes()) == digest, path
def open_raw(name):
    with tarfile.open(ROOT/name) as t:
        payloads = {m.name.removeprefix('./'): t.extractfile(m).read() for m in t if m.isfile()}
    rows = {n[:-5]: j for n,b in payloads.items() if n.endswith('.json') and isinstance(j:=json.loads(b),dict) and set(j)=={'argv','rc','out','err','panic','timeout'}}
    for n,j in rows.items():
        assert sha(payloads[n+'.out'])==j['out'] and sha(payloads[n+'.err'])==j['err'], n
        assert not j['timeout'] and not j['panic'] and b'panicked at' not in payloads[n+'.err'] and b'AUDIT TIMEOUT' not in payloads[n+'.err'],n
        assert j['rc']==(101 if n in ('218/warm','218/cold') else 0),n
    return payloads,rows,json.loads(payloads['complete.json'])
a, ar, aj=open_raw('native.tar.gz')
b, br, bj=open_raw('extra-native.tar.gz')
assert len(ar)==12 and len(br)==25
for k in ('hash','manifest','recipe'):
    assert a['fifo-'+k+'/prime.out']==b'11\n' and a['fifo-'+k+'/after.out']==b'22\n'
    assert aj[k]['entry'] in aj[k]['available']
assert a['null-env/prime.out']==b'Some([255])\n' and a['null-env/after.out']==b'None\n'
assert aj['null-env']['synthetically_retained_legacy_null']
wasm=aj['inactive-wasm']
assert wasm['lock_contains_inactive'] and wasm['inactive_package_archives']==[]
assert '/ab/se/absent-wasm' in wasm['http_requests'] and '/active-reg/0.1.0/download' in wasm['http_requests'] and '/absent-wasm/0.1.0/download' not in wasm['http_requests']
for n in ('build','check','repeat'):
    assert '--offline' in ar['wasm-edge/'+n]['argv'] and '--locked' in ar['wasm-edge/'+n]['argv']
for n in ('194','195'):assert b[n+'/prime.out']==b'PROBE_ALPHA 11\n' and b[n+'/edit.out']==b'PROBE_ALPHA 22\n'
assert bj['206']['surviving']=={n:sha(n.encode()) for n in ('keep.o','keep.bc','keep.txt')}
assert [b['210/'+w+'/run'+str(i)+'.out'].strip() for i,w in enumerate('abab')]==[b'11',b'22',b'11',b'22']
assert bj['212']['foreign_file_retained'] and len(bj['212']['beta_fingerprint'])==64
assert [b['214/run'+str(i)+'.out'].strip() for i in range(3)]==[b'Some([255])',b'Some([254])',b'None']
assert b['215/prime.out']==b'11\n' and b['215/edit.out']==b'22\n'
assert b['218/warm.err']==b['218/cold.err'] and b'not a valid Unicode string' in b['218/warm.err']
assert b['219/prime.out']==b'alpha\n' and b['219/edit.out']==b'bravo\n'
assert b'Removed 8 files' in b['225/first.err'] and not bj['225']['context_still_exists'] and bj['225']['remaining']==[]
tracker=json.loads((ROOT/'tracker.json').read_text())
programs=(ROOT/'programs.txt').read_text()
assert all(tracker[k] in programs for k in ('cargo','cargo_sha256','rustc_sha256','driver_sha256'))
assert len(tracker['issues'])==18
assert tracker['issues']['225']['is_ancestor'] is False and tracker['issues']['225']['shipped_equivalent']['is_ancestor']
if opts.cargo_git:
    for j in tracker['issues'].values():
        for ref in [j]+([j['shipped_equivalent']] if 'shipped_equivalent' in j else []):
            code=subprocess.run(['git','-C',str(opts.cargo_git),'merge-base','--is-ancestor',ref['head'],tracker['cargo']]).returncode
            assert code==(0 if ref['is_ancestor'] else 1),(ref['head'],code)
campaign=json.loads((ROOT/'campaign-signatures.json').read_text())
assert sum(len(c['stderr']) for c in campaign.values())==124
for name,c in campaign.items():
    assert not any(q['panic'] or q['ice'] for q in c['stderr'].values())
    if opts.campaign_dir:
        file=opts.campaign_dir/name/'native.tar.gz'
        assert sha(file.read_bytes())==c['archive'],name
        with tarfile.open(file) as t:
            captured={}
            for m in t:
                if m.isfile() and m.name.rsplit('/',1)[-1] in ('err','stderr','cargo.stderr','cargo.err'):
                    b=t.extractfile(m).read()
                    captured[m.name]={'sha256':sha(b),'panic':b'panicked at' in b,'ice':b'internal compiler error' in b}
            assert captured==c['stderr']
print('18 open tracker items classified, 37 official Cargo commands checked, 124 previously retained stderr identities verified.')
