from pathlib import Path
import hashlib,json,random
D=Path(__file__).resolve().parent
domain=b'Ohm release 1.99.0-16 independent current-stack historical build-script timestamp confirmation; 4c07cbf6; 2026-10-27.'
seed=int.from_bytes(hashlib.sha256(domain).digest()[:8],'big');rng=random.Random(seed);events=[]
for direction in ('reverse','restore'):
    order=[['parent','candidate']]*6+[['candidate','parent']]*6;rng.shuffle(order)
    events.extend({'direction':direction,'direction_pair':i+1,'arm_order':v} for i,v in enumerate(order))
rng.shuffle(events)
for i,v in enumerate(events):v['order']=i+1
def write(n,x): (D/n).write_text(json.dumps(x,sort_keys=True,indent=2)+'\n')
def sha(p):return hashlib.sha256((D/p).read_bytes()).hexdigest()
write('order.json',events)
write('plan.json',{
 'title':'Conditional prospective independent whole cargo check confirmation on shipped Cargo source 1.99.0-16',
 'admission':'Run only if the earlier stack qualifies at its registered threshold; keep its results and inference separate. No current-stack outcomes were consulted when choosing order, sample size or fixture.',
 'upstream_cargo_git':'4c07cbf6bd91e170e3b8904eeb82436a6dbde358',
 'treatment':'Apply exactly the same two hunks in source-delta.patch, including its new checked-in unit regression, to upstream_cargo_git. Publish resulting Git commit and tree proofs before scoring. Both touched function bodies were identical between the calibrated earlier parent and -16 on preregistration.',
 'source_delta_from_earlier_base_sha256':sha('source-delta.patch'),
 'ruff_git':'93526150df078af7dd8fc4226cdcc469539d2001',
 'real_ruff_edit':'a8ba9e0458e60f8c406216778f0ea1cc3759c9b2, full linked Git watch fix reversed and restored, three complete build.rs files',
 'main_patch_sha256':sha('main.patch'),'secondary_generated_fixture_sha256':sha('pydantic.patch'),'secondary_details_sha256':sha('holdout.json'),
 'workload':['cargo','+ohm','check','--locked','--offline','--message-format=json','-j8'],
 'independence':'24 new pairs ordered by a distinct frozen seed. A private current-compiler target/shared/registry lineage, separate immutable four source/arm starting snapshots and fresh per-episode copies. Require each state and episode to pass real 520-fresh preflight. Do not share issued episodes or measured ms with the earlier study. Initial seeds may reuse immutable dependency bytes through separate copies, but must build/check against the current compiler/runtime and be verified with real processes. No mtime interventions. Restore the authentic linked checkout after each private source view.',
 'source_and_release':'Build matched release-profile PGO control and treatment from same verified full input manifest and same compiler/SDK/profile. Require a second independent byte-identical parent. Use only the already-validated Ohm SDK LLVM packaging with whole ELF/loader/RELRO guards, or directly identical raw release outputs if their regular production packaging supplies A/A exactness. Publish immutable recipe, packaging choice and all actual source/compiler/Cargo/LLVM SHAs before timing. Run an unmodified -16 packaged stock physical calibration once its official archive digest is authenticated. In addition, require raw-versus-packaged source-build rosters to match if packaged images are the scored subjects.',
 'functional':'Run ordinary untimed and physically traced reversals/restorations before and after scoring. Verify counts of genuine full and link-only rustc, Wild and the three real scripts, all 520 artifacts, unchanged warnings and script/metadata evidence. Establish that the changed script still executes, a true directive or external included file still changes native output or fails like a clean build, and the second historical Pydantic generation produces the correct ZIP member on each current arm. The historically observed 3→0 repeated check may be neutral or absent on this new stack; retain such an outcome and do not publish a current-stack improvement if it fails the checks.',
 'trial':'12 reverse and 12 restore randomized paired episodes, six parent-first per direction. Each arm times one full changed check, its first untouched check, and its second untouched check. 144 ordinary, untraced commands. Native lock, CPU 0–23/-j8, same logical paths, normal exit and stdout/stderr included in the monotonic clock. No tracing, checksum analysis, or command setup between the starts except ordinary file opening and process dispatch. Exclude copying/namespace startup. Record all admissions and failures.',
 'order_sha256':sha('order.json'),'seed':seed,'seed_domain':domain.decode(),
 'inference':'For each pair and three endpoints (changed, first untouched, their sum), log(C/P), then 100*(1-exp(mean)) reduction. Compute two-sided exact randomization conditional on six C-first per direction across the 924×924 assignments. Holm .05 across these three, direction-stratified percentile bootstrap 100000 samples with seed 278432. Claim speedup only if Holm-adjusted p<.05 and the full 95% reduction interval is positive. Both per-direction rows and second untouched descriptive measurements retained. No inference pooled with the earlier cohort.',
 'failure':'If an input, source equivalence, changed-mode behavior, diagnostic, exact A/A, byte-level loader, native integrity, or resource gate fails, preserve it and withhold the affected result. Maintain 25GiB home and 10GiB measurement-tmpfs reserves; no competing native jobs.',
 'previous_preregistered_protocol':'https://github.com/astral-sh/ohm-cargo/tree/30c4bfb6a1989da3818a2381b6cd46cd39c0e50e/benchmarks/ruff-dev-loop-20261027/build-script-timestamp-timing-plan',
 'packaging_protocol':'https://github.com/astral-sh/ohm-cargo/tree/9bf9bf535d6838c3243d0daebf0b911670a00a5a/benchmarks/ruff-dev-loop-20261027/build-script-packaging-amendment'})
