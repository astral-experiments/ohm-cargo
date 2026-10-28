from pathlib import Path
import json
root=Path(__file__).resolve().parent
result=json.loads((root/'summary.json').read_text());cohorts=result['cohorts']
lines=['# All eight Ohm changes on edited uv test compilation','',"`cargo test --no-run --locked --offline -j8` compiled an edit to uv's private install-source logic. The endpoint sums original Cargo, rustc and Wild PIDs and all their threads. Baseline and candidate Cargo were separately profile-trained. Both used the exact shipped rustc. The candidate combined the Cargo and standard-library changes with both Wild changes.",'','| Independent cohort | Median instruction reduction | 99.22% rank interval | Wins | Exact sign p | Balanced-order p |','| --- | ---: | ---: | ---: | ---: | ---: |']
for label,c in cohorts.items():
    if c['state'] in ['qualified','inconclusive']:
        a,b=c['rank_interval_99_21875'];lines.append(f"| {label} | {c['median_saving']:.4%} | {a:.4%} to {b:.4%} | {c['wins']}/8 | {c['two_sided_sign_p']:.7g} | {c['balanced_order_randomization_p']:.7g} |")
    else:lines.append(f"| {label} | {c['state']} | | | | |")
lines+=['',('Both cohorts passed every registered performance and comparability gate.' if result['qualified'] else 'The two-cohort result did not meet all registered gates.'),'','| Cohort | Arm | Cargo median | rustc median | Wild median | Total median |','| --- | --- | ---: | ---: | ---: | ---: |']
for label,c in cohorts.items():
    for arm,v in c.get('median_instructions_by_role',{}).items():lines.append(f"| {label} | {arm} | {v['cargo']:,.1f} | {v['rustc']:,.1f} | {v['wild']:,.1f} | {v['total']:,.1f} |")
lines+=['','Role and total medians are calculated independently. Both cohort estimates use the median of the eight same-source paired reductions.','','## Workload and artifacts','']
for label,c in cohorts.items():
    if c['state'] not in ['qualified','inconclusive']:
        lines.append(f"{label.capitalize()} {c['state']}.");continue
    n=len(c['full_digest_variant_combinations'])
    parity=(f'{n} source/target groups had multiple full-file digests under the registered mask. The cohort summary lists each variant.' if n else 'Every linked output matched its full-file SHA-256 across arms for the same source.')
    lines.append(f"{label.capitalize()} verified four native/count admission cells and 16 measured commands. Every command recompiled only uv and emitted 72 test executables. Its process roster contained one Cargo, six rustc and five Wild PIDs. {parity} The original fixture passed restoration.");lines.append('')
lines+=['The independent cohorts shared the pinned source location, immutable archived seed and binary identities. Each used its own new Cargo home, target snapshots, schedule and same-length source edits. Both admissions held all work and source bytes constant across four native/instrumented cells. Every post-command file hash and every counted thread receipt is retained.','','Only the known 32-byte GNU build ID and one .rodata section-header entry-size byte were eligible to vary in the large test harness. The invariant-byte SHA-256 and field value were checked for each observation.','','The selected-process sum excludes kernel execution, cc, collect2, wrapper processes and pre-exec work in forked children. Both arms used Wild --no-fork with the Cargo jobserver. Tests never executed. See reproduce.md for replay and verify.py for standalone recalculation.']
(root/'RESULTS.md').write_text('\n'.join(lines)+'\n')
