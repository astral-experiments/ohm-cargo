#!/usr/bin/env python3
"""Freeze balanced paired whole-command timings before either candidate is scored."""
import hashlib,json,random
from pathlib import Path
out=Path(__file__).resolve().parent/'holdout-plan.json'
seed=bytes.fromhex('021202617aadc559052f06419ce29011d0162d9c46f599510542cd22590d044b')
plan={'workload':{'ruff':'93526150df','patch':'1797ed542380c5aa0f7832e3877b1df56ddb2e08','file':'crates/ty_ide/src/docstring.rs','variants':{'original':'Ruff pinned worktree','edited':'reverse the exact historical patch against the pinned worktree'}},
'parents':{'cargo':'211465de4b9e4589da2be06871acd9304dd3b94c849c1304f723484cb4f71dfc','driver':'539e8623c70298849aa3043f35374ea3c7dc7215aac44011e64fccdc818f91a4','wild':'0d6335808b647d499f3d74993b602e64ff0625206c809bf4913c487eea380cd5','candidate_driver':'c61eaa6cc336b48958e7712104e09182a287f2a33b4aa181b16a535c08e6a824','candidate_cargo':'publish exact frozen R14-profile PGO SHA before scoring; keep the same native linker and stage2 frontend/sysroot'},
'cohorts':{},'affinity':'local CPU 0-3, CARGO_BUILD_JOBS=4; possible later isolated 8/16-core independent replication reported separately',
'procedure':'For each arm, run the measured source once untimed, then the opposite variant once untimed using that same arm. Time a whole ordinary, native cargo +ohm build --locked --offline or cargo +ohm test --no-run --locked --offline with the measured source. Exclude any output hashing and trace diagnostics from the command wall endpoint. Candidate and parent always compile/link at the same absolute workspace, target, tool and trust paths. No tests execute.',
'oracles':'Use exact native full reference for both variants of each command. Every timed run must have correct ordinary terminal/exit, exact golden SHA256s for all 6 build or 102 test ELFs, same root dynamic exports, raw .so and standalone metadata, and ordered .rlib codegen payloads and embedded metadata. Verify current source and physical tool identity, stable registry proof inventory and compiler-mode roster. Require the stock full compiler and candidate link-only for the mixed ty_wasm unit. Native linker still runs; preflight full strace records compare actual link invocations. Archive member salts may vary and are separately reported.',
'exclusions':'Stop and disclose any unexpected graph, missing proof, failed output, source/namespace change, disk guard, fallback on an eligible trial, or affinity failure. Rerun affected fixed-design cohort only after correcting an external invalidation; preserve raw failures. Do not drop slow valid samples or select alternate commands.',
'analysis':'Two primary median paired wall reductions (parent-candidate)/parent. Require at least 10/12 favorable per command, positive median in each edit direction, two-sided distribution-free lower median bound >0 (3rd and 10th order statistics, 96.14% coverage), and one-sided paired randomization p passing Holm across the two commands. Enumerate the 400 assignments per command balanced within edit direction (3 of each 6 assigned parent-first). Use the mean signed log wall difference for the randomization test, and call a >1% median required for filing. Report both directions and relative medians, all pairs and process counts. Native scope is local 4-core pending independent scaling.'}
for mode in ('build','test-no-run'):
 rng=random.Random(int.from_bytes(hashlib.sha256(seed+mode.encode()).digest(),'big'))
 pairs=[{'variant':v,'order':o} for v in ['original','edited'] for o in ['PC','CP'] for _ in range(3)]
 rng.shuffle(pairs);plan['cohorts'][mode]=pairs
out.write_text(json.dumps(plan,indent=2,sort_keys=True)+'\n')
print(hashlib.sha256(out.read_bytes()).hexdigest())
