"""Render every original pair after the registered native run reaches terminal."""
import json,runpy
from pathlib import Path
d=Path(__file__).resolve().parent
r=json.loads((d/'results.json').read_bytes())
s=runpy.run_path(str(d/'verify.py'))['check'](r)
rows=r['all_16_slots']
out=['# Ordinary Ruff archive mechanism screen on replacement Milan','']
if r['terminal_exit']==0:
 status='passed'if s['eligible_for_optimized_trial']else'failed'
 out += [f"The Milan stage1 archive screen **{status}** its registered mechanism gate. All eight pairs completed, with 32 ordinary Cargo commands. {s['positive']}/8 pairs had a positive conservative archive saving. The median lower-bound saving was {100*s['median_conservative_savings_as_fraction_of_loop']:.2f}% of the ordinary A edit-plus-repeat, and the median whole-loop B/A ratio was {s['median_full_loop_ratio']:.4f}. The gate required six positive bounds, a median of at least 1%, and a whole-loop ratio of at most 1.02.",'',
 '| Pair | Source | Order | A edit + repeat, s | B edit + repeat, s | A lower minus B upper archive time, ms |','|---:|---|---|---:|---:|---:|']
 for i,(ordering,which)in enumerate(r['schedule'],1):
  v={e['arm']:e['after']for e in rows if e['pair']==i}
  loop=[(v[k]['edit_ns']+v[k]['repeat_ns'])/1e9 for k in 'AB']
  margin=(v['A']['archive_lower_ns']-v['B']['archive_upper_ns'])/1e6
  out.append(f"| {i} | {'P edit' if which=='parent' else 'H restore'} | {ordering} | {loop[0]:.3f} | {loop[1]:.3f} | {margin:.1f} |")
else:
 out.append(f"The original terminal failure stopped this host with exit {r['terminal_exit']}. {s['complete_pairs']} pairs and {s['verified_slots']} arm visits passed all native checks, and {s['recorded_command_results']} ordinary command results were retained. The terminal reader produced no partial effect.")
out+=['','Both arms ran the ordinary Ruff package build and its immediate unchanged repeat at the canonical source and SDK paths. The passive observer ran on CPU 8, and the ordinary processes used CPUs 0–7. Complete archive hashing, literal bytes comparison and native caller checks ran after both command clocks. [Registered design](https://github.com/astral-sh/ohm-cargo/tree/86fd410922315ae22b9d3de58f50b30ba1e8939a/benchmarks/ruff-dev-loop-20261027/rc19-rlib-observed-name-screen-plan) · [Milan native evidence](https://github.com/astral-sh/ohm-cargo/tree/262963ad54125a4597aacee71ca500e159f594fd/benchmarks/ruff-dev-loop-20261027)',
'','Run the SHA256SUMS check, then run selftest.py and verify.py with Python 3. The reader replays the exact randomization, reconstructs each command wall time and archive creation/publication bounds from its raw passive event record, counts the 10/0 Cargo compile lines, and checks the 452-path roster and authenticated 101,719,820-byte archive and program digests. The export preserves original stdout and stderr digests, and replaces private path prefixes in the diagnostic text. These measurements use the stage1 compiler. A production optimization would require its own independently qualified whole-command trial on both hosts.']
with (d/'README.md').open('x')as q:q.write('\n'.join(out)+'\n')