Verify `SHA256SUMS` from this package before use. `RAW-MANIFEST.json` records the
original archive hashes, every remote member and every collected local envelope
file. Extract `raw-results.tar.gz` into a new directory. Under
`captures/{ir-failed,ir-closed,native}/`, each `payload.tar` is the exact original
transport archive, including full Callgrind profiles and all stdout/stderr.
Its adjacent transfer manifest is unchanged. Never overwrite the original
archives or results while replaying analysis.

The readable `evidence/benchmark/frozen/paired.py` and `paired_repeated.py` are
the exact frozen runners. To recompute summaries on disposable copies of a
completed workflow directory, use their actual parser options:

```
python3 evidence/benchmark/frozen/paired.py analyze COPIED_IR_WORKFLOW --confidence 0.99 \
  --resamples 20000 --seed 1701 --minimum-pairs 12 --minimum-improvement 0.01
python3 evidence/benchmark/frozen/paired_repeated.py analyze COPIED_NATIVE_WORKFLOW --confidence 0.99 \
  --resamples 20000 --seed 1701 --minimum-pairs 30 --minimum-improvement 0.01
```

The raw records retain original absolute log/profile paths. These generic
analyzers recompute from the local JSON tables and need no path edits for summary
replay. Keep the scripts together in their `frozen/` directory: the repeated
adapter imports its adjacent core from that layout. The independent reviewer
additionally resolves recorded paths against the collected `remote/` directory
and checks the full logs/profile hashes without rewriting evidence. Its complete
original and transport-lineage source is retained under `lineage/local/` and
in the collected envelopes. Prefer that reviewer for a full integrity replay.

The generic runner's built-in screen is not the experiment's complete acceptance
policy. The exact frozen driver/protocol and retained `gate.json` define the
instruction gate and native regression check. A comparison needs the fixed count,
at least 1% geometric-mean reduction, a positive 99% lower bound, exact two-sided
sign p at most 0.01, and positive reductions in both AB and BA orders. Bootstrap
uses 20,000 paired resamples with seed 1701. Native inference uses 30 pairs of
eight-call group sums; individual calls are not 240 independent observations.

For a new measurement, rebuild the exact baseline and candidate source trees from
the retained cohort patches using the same source directory, target directory,
compiler and actual rustc flags for both variants. Preserve separate immutable
binary copies and build/strip receipts. Runtime binaries and dependency/target
payloads are excluded from this evidence archive; the source/build/strip records,
runtime download identities and setup controls specify them. The measured binary
hashes apply to the retained cohort, not to arbitrary rebuilds on another host.

The evidence checkout itself may live at any workspace prefix. The original
remote controls use a separately owned fixed `/tmp/ohm-hillclimb-20261021-inheritance-measurement`
root and explicit host assertions. Their staging path must be absent. Adapting
the host or that fixture root requires a prospective source/configuration freeze
and independent review. Translate every path consistently before staging, while
keeping one identical canonical Cargo executable path, uv source path, target
path and shared-cache path for baseline and candidate within each workflow.
Use the runner's atomic variant install; do not invoke variants by different
executable names or alternate per-variant target paths.

Keep uv at `3d82a6ad5a7eab8c68236553b7846517767c4b61` with no source edit. Each
workflow has an independent fresh target/cache. Run the exact fixed three-call
untimed warm sequence, strict zero-child execve trace and cross-switch proof
before sampling. Record ancestor Cargo configuration presence and content,
the ordinary system SSL trust paths, runtime/tool/binary hashes and host identity.
IR uses the recorded Callgrind environment wrapper with trace-children disabled;
its elapsed times are not native timings. Native has no profiler preload.

Use the original fixed seeds: IR check/test 20261021111/112, native check/test
20261021113/114. Each workflow has two warmup pairs. Finish and audit both workflows
before effects; do not pool with old binaries, omit samples or extend a batch.
Only launch native after both instruction gates qualify. Preserve guard and
transport failures. The retained admissions/closure lineage documents this run's
operational handling; it is not permission to replace observations in another run.

Final native findings and the exact final recovery/reviewer command are pending
the terminal phase review. This draft is not an assembled publication artifact.
