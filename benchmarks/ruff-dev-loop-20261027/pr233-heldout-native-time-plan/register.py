from hashlib import sha256
from pathlib import Path
import itertools, json, random

root = Path(__file__).resolve().parent
names = ['lexer-pending-indentation','signed-pattern-diagnostic','single-string-allocation']
eps = [(mode,edit) for mode in ('build','test') for edit in names]
def perm(seed, seq):
    rng=random.Random('Ohm Ruff heldout phases v1 2026-10-27\x00'+seed)
    out=list(seq);rng.shuffle(out)
    return out
orders={f'{m}/{e}/{d}':perm(f'{m}/{e}/{d}',[['B','C']]*4+[['C','B']]*4) for m,e in eps for d in ('edit','restore')}
rounds=[perm(f'block-{i}',eps) for i in range(8)]
sequence=[]
for block, mixed in enumerate(rounds,1):
    for mode,edit in mixed:
        for direction in ('edit','restore'):
            order=orders[f'{mode}/{edit}/{direction}'][block-1]
            sequence.append(dict(block=block,mode=mode,edit=edit,direction=direction,arms=order))
plan={
 'purpose':'Prospective elapsed-time replication of Rust #232 against corrected #233 for all three complete historical Ruff parser reversals on a different machine from the earlier timed diagnostic edit. Selected after first unscored build process counts were available; no ordinary paired elapsed observation from these release drivers on these additional edits was used to select endpoints or run orders. No claim about other source changes.',
 'host':'H5 charlie-ohm-loader-perf-1024, AMD EPYC-Genoa, 32 vCPUs, Linux 7.0.0-38-generic, CPU affinity 0-23, CARGO_BUILD_JOBS=8.',
 'source_plan':'d8d5011852778f8babeb4e5c3cb0613c6793ca6c','source_sha256':'a55a3d97d1f4880a3c516b930b77ca49e337927a1404a4e0dafa23222244d7e4',
 'qualified_runner':'39eaf6a145d10d7e018a7247d6858a1830002adb','qualified_binding_sha256':'74b5d88f422ccb9751653ca595d99a78c95c8b469f1d83a5749b7db1cdc99d3a',
 'ruff':'93526150df078af7dd8fc4226cdcc469539d2001',
 'arms':{'B':{'rust_commit':'8ce2f21e25c06e7f884ca7b5c4e7898180791ae4','driver':'051b9d3f5861f984faa0f8c1d2ab9b5c28e483a05c728051de837291c83fd518'},'C':{'rust_commit':'27029b4bce40f3b5497add5019c02a11c16c4c18','driver':'dec72d1e68fdb0f8ff91fc98e8a826bf837878eca30b1ec5ea2f3258b6b2f99f'}},
 'cargo_commit':'d38fdd02503662de04c52f5f370f5dd81bddf868','cargo_sha256':'dd5cab154b8dcd09ccc2753160d314cade80979b2d055ee66aa9e2217e05e7e1','wild_sha256':'0d6335808b647d499f3d74993b602e64ff0625206c809bf4913c487eea380cd5',
 'endpoints':[{'mode':m,'edit':e} for m,e in eps],'pairs_per_endpoint':16,'sequence':sequence,
 'design':'Eight rounds. Each round visits all six mode/edit endpoints in separately shuffled order. For each endpoint first reverse the complete historical patch in both arms, then restore both to original Ruff. Each direction has eight independent B/C-order assignments, exactly four in each order. Total 96 paired transitions, 192 ordinary complete Cargo commands. No Rust test binary is executed by Cargo.',
 'primary':'Elapsed process time measured from spawn to exit of cargo +ohm build (or cargo +ohm test --no-run) --locked --offline --message-format=json with regular stdout/stderr files. Source switching, namespace setup, artifact validation, runtime witnesses, immediate no-op and tracing are outside the timer. Measure exactly the two compared binaries on each endpoint, in all scheduled orders.',
 'inference':'For each mode/edit estimate mean paired log(C/B). Report median elapsed per arm, paired geometric percent elapsed reduction, simple paired winning count, 95% 20,000-resample block percentile interval (resample eight complete edit/restore round pairs with replacement; deterministic seed 2026102701 + endpoint index). Two-sided conditional randomization statistic is absolute summed log ratio; each exact assignment puts C second in four out of eight pairs in each direction independently (70 squared = 4,900). Holm adjust all six endpoint tests. Significant gain requires positive geometric reduction and lower interval endpoint and Holm-adjusted p<0.05. Report all adverse, null and positive endpoints; separate direction medians are descriptive.',
 'admission':'Both unscored whole-workspace runs must finish from their registered empty states, all immediate zero-job checks pass and all study sources return to original. Require exclusive H5 measurement lock, no active compiler/linker benchmark or competing CPU-heavy job on the timed CPUs; finish read-only graph and metadata capture or move/postpone heavy decoding before scores. Use new scratch stores copied from the four completed H5 states. Preserve all four original physical states. Verify private copies genuinely settle (per-arm complete final roster, empty/qualified messages, fresh Cargo control) and reproduce physical rustc/Wild counts on an unscored edit/restore in each arm/mode before starting. Require 25 GiB free throughout. Discard incomplete families if any integrity check fails, no restarts for slow observations.',
 'validity':'Every counted command must match the original unscored Cargo unit, ELF and executable roster and dirty target list for that arm, mode, source and direction. Each following audited command must be fully fresh. Check the two signed-pattern, original t-string/RUF008 and valid source diagnostics against frozen expectations. Compare raw and release-normalized rosters; use only the two explicit path namespaces from the independently verified H5 source runner. Record endpoint order, stderr/stdout hashed, outcomes and exclusion/abort details. Finish with a second source-restoration and native process-count control on each mode/edit combination. Keep all measured data including runs affected by normal noise. No study-specific runtime compiler flags.',
 'same_units':'501 build units, 619 test-compilation units; package, source manifest, target, profile, features, remaining filenames/executables and diagnostics must agree across the registered namespace distinction.',
}
val=json.dumps(plan,sort_keys=True,indent=2)+'\n'
dest=root/'plan.json'
if dest.exists():assert dest.read_text()==val
else:dest.write_text(val)
print(sha256(val.encode()).hexdigest())
