"""Choose order independently of measured work and bind the two Cargo arms and compiler."""
from pathlib import Path
import hashlib
import json
import random

here=Path(__file__).resolve().parent
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
seed=int.from_bytes(hashlib.sha256(b'Ohm same compiler full Ruff guarded mixed libraries after allocation identity, paired Cargo marginal, first prospect, 2026-10-27').digest()[:8],'big')
rng=random.Random(seed);orders={}
for mode in ('build','test'):
    split={}
    for direction in ('edit','restore'):
        value=['BC']*5+['CB']*5;rng.shuffle(value);split[direction]=value
    orders[mode]=[{'direction':direction,'order':split[direction][i]} for i in range(10) for direction in ('edit','restore')]
plan=dict(ruff='93526150df078af7dd8fc4226cdcc469539d2001',edit='3ea20f6161cbf59cb56595dfb634ec24bfa82f0b',orders=orders,seed=seed,
    qualification_protocol='da50f3cb8a6071b604bb60737084093dc4caef313fba4569c0ded9dba478a2bc',original_support='59ca9193f8f6ddf4cff22ab023cc41733200d251f42e3400635f0e81c42a5d71',
    compiler='63145e253973980f3786ce562b2342d2590b4a783256e4197e8ffacdf7d110fa',cargo={'B':'dd5cab154b8dcd09ccc2753160d314cade80979b2d055ee66aa9e2217e05e7e1','C':'0f237cc3b506aa90c1224e6ed80f646566b424b78c8d74f288f6523d17fc8aa1'},
    source_cargo={'B':'d38fdd02503662de04c52f5f370f5dd81bddf868','C':'190d261a8546f121e3aa1adf237d85e02164eb18'},
    units={'build':501,'test':619},bootstrap_seeds={'build':160827,'test':160828},runner=sha(here/'study.py'),analyzer=sha(here/'analyze.py'),
    authorization='Only after the full unscored mixed-allocation protocol qualifies both modes with every independent reference and ordinary Rust caller, its complete raw-results manifest is public, and the host, code, output hashes and human-readable GO grant revalidate. No unscored elapsed observations enter analysis.',
    workload='Twenty adjacent paired changes per command, with ten genuine edits and ten genuine restorations. H3 CPU 0–23, jobs 8. Workload is an ordinary cargo +ohm build --locked --offline or cargo +ohm test --no-run --locked --offline, including startup and the final Cargo terminal, no trace and no tests executed inside the clock. One separately traced all-fresh followup authenticates each scored job and Ruff CLI diagnostic.',
    history='Private, different-inode copies of each fully trained Cargo state. Verify the on-disk bytes, mode and mtime of every reported artifact. Qualify both copied arms in each direction before scoring, and requalify them again after every scheduled pair is complete. The fixed alternating edit/restore chronology gives each arm exactly the same sequence of source changes. Within each direction, a seeded 5/5 split puts each Cargo first equally often.',
    statistics='Paired geometric mean wall-time reduction, medians by arm, direction-stratified 100,000-resample paired bootstrap 95% interval, counts per direction, and exact two-sided randomization of early/late arm assignment within each direction (choose(10,5)^2=63,504). Holm across build and test. Both must have adjusted p<0.05, lower 95% bound above 1%, and positive effects in both directions to qualify this combined performance claim. No exclusion or rerun based on time. Report failed structural or timing gates without a qualified claim.',
    scope='Only the Cargo marginal for requesting two rustc guarded native jobs with a common independently rebuilt experimental compiler. It cannot establish a Rust compiler marginal, the end-to-end speed of an integrated current release, or the speed of other Ruff edits. A later Rust or shipping PR requires its own qualifying comparison.')
(here/'plan.json').write_text(json.dumps(plan,indent=2,sort_keys=True)+'\n')
