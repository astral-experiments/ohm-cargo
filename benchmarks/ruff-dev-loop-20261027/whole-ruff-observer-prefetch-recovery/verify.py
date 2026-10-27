"""Verify the recorded unscored missing-proof trajectory and lossless ELF differences."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import tarfile

p=argparse.ArgumentParser(description=__doc__);p.add_argument('--original-target',type=Path);args=p.parse_args()
root=Path(__file__).resolve().parent
with tarfile.open(root/'recovery-records.tar.gz') as t:
    raw={m.name:t.extractfile(m).read() for m in t if m.isfile()}
    assert len(raw)==len(t.getmembers())==18
s='prefetch-v2-missing-proof-supplement/'
get=lambda rel: json.loads(raw[s+rel])
sha=lambda data:hashlib.sha256(data).hexdigest()
assert raw['prefetch-v2-recovery-helper/supplement.rc'].strip()==b'1'
assert b'private clone differs from sealed native workspace' in raw[s+'failure.txt']
ex=get('clone-rejection.json');assert sha(raw[s+'clone-rejection.json'])=='a1486a1f189f5cee993ce92b033da6ec65254381c76beaecdf83ff00ac84a230'
assert ex['original_primary_statistics_sha256']=='f49971aeba6754e25c3a0e06ef1c966bfda99ce5bd7ac28c6f1e347ba3b1afa9'
a=get('recovery-V-initial-anchor-attempt-1/anchor.json');z=get('recovery-V-final-anchor-attempt-1/anchor.json')
g=json.loads(raw['whole-ruff-observer-prefetch-fifo-v2/final-test-V/anchor.json']);assert g['raw_sha256']==a['raw_sha256']
for k in ('units','roster','roster_sha256','messages','message_sha256','executables','elf','diagnostics','scanned_compiler_dep_info'):
    assert g[k]==a[k]==z[k],k
assert z['units']==619 and len(z['executables'])==102 and len(z['elf'])==110
assert all(len(q['exec_open_calibration'])==1 for q in (a,z))
for k in ('proofs','passive_proofs'):
    for q in (a,z):assert len(q[k])==1 and q[k][0]['complete'] and q[k][0]['raw_sha256']==g[k][0]['raw_sha256'] and q[k][0]['sha256']==g[k][0]['sha256'],k
assert a['passive_proofs']==z['passive_proofs'];assert sha(raw[s+'removed-complete-V.bin'])==g['proofs'][0]['sha256']
for n,full,loan,dirty,complete in [(1,1,50,56,False),(2,1,50,56,True),(3,0,0,0,True)]:
    r=get(f'recovery-V-learn-{n}/receipt.json');proc=r['processes'];expected=Counter({'full':full,'link-only':loan});assert len(r['dirty'])==dirty and r['status']==0 and r['units']==619
    assert r['training_proof_state'][0]['complete']==complete and r['passive_training_proof']==a['passive_proofs']
    assert Counter(v for _,v in proc['rustc'])==+expected and ([k for k,v in proc['rustc'] if v=='full']==(['ron'] if full else []))
    assert len(proc['linkers'])==loan and not proc['target_execs']
for tag in ('initial-prepare','initial-anchor-attempt-1','final-anchor-attempt-1'):
    r=get(f'recovery-V-{tag}/receipt.json');assert not(r['dirty'] or r['processes']['rustc'] or r['processes']['linkers']) and r['status']==0
assert set(a['raw_sha256'])==set(z['raw_sha256']);changed={k for k in z['raw_sha256'] if a['raw_sha256'][k]!=z['raw_sha256'][k]};assert len(changed)==3 and changed==set(ex['diff'])
ret=get('copy-retired.json');delta=get('copy-exact-deltas.json');assert ret['deltas']==delta['deltas'] and ret['C_never_created'] and ret['bytes_free_after']>ret['bytes_free_before']
assert not any('recovery-C-' in key for key in raw)
for name in changed:
    row=ret['deltas'][name];w=ex['diff'][name];old=w['physical_original_now'];new=w['clone_now']
    assert old['content_with_two_wild_fields_masked']==new['content_with_two_wild_fields_masked'] and old['size']==new['size'];assert row['sha256_before']==old['raw']==a['raw_sha256'][name] and row['sha256_private']==new['raw']==z['raw_sha256'][name]
    edits=row['bytes'];assert len(edits)==33 and [off for off,_,_ in edits[:32]]==list(range(edits[0][0],edits[0][0]+32)) and edits[-1][0]>edits[31][0]
    assert bytes(a for _,a,b in edits[:-1]).hex()==old['gnu_build_id'] and bytes(b for _,a,b in edits[:-1]).hex()==new['gnu_build_id'];assert edits[-1][1:]==[old['rodata_entsize'],new['rodata_entsize']]
    assert all(a!=b for _,a,b in edits)
    if args.original_target:
        rel=Path(name).relative_to('/mnt/devbox-scratch/dev-user/ohm-whole-skips-20261027/native-target');data=bytearray((args.original_target/rel).read_bytes());assert sha(data)==row['sha256_before']
        for off,a,b in edits:assert data[off]==a;data[off]=b
        assert sha(data)==row['sha256_private']
print('Verified the V-only supplemental rejection, 56/56/0 dirty units, exact reconstructed observer bytes and 33 changed bytes in each of three ELF files. The original timing remains unchanged.')
