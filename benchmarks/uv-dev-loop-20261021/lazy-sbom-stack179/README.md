This package measures skipping unused SBOM construction on the exact PR179 parent. Candidate `4e5d21f61600cf333adbe5a96f51d74ea14b3060` has tree `c377ade816d378aa75f629313ac7b116da10c6da`; its parent is `19718e6d1637244ffbb193334f50bae3ffca1be5`. The uv revision is `3d82a6ad5a7eab8c68236553b7846517767c4b61`.

The primary dirty `cargo test --no-run` workflow used 5.540825% fewer Cargo-process instructions, with a 99% interval of 5.445090–5.597544%. All 12 measured pairs improved (two-sided sign p = 0.00048828125), and both execution orders improved. This passes the prospective 1% instruction gate.

The secondary dirty `cargo check` workflow used 0.529876% fewer Cargo-process instructions, with a positive 99% interval of 0.435103–0.606160%. All 12 pairs improved, but this result is below the 1% minimum and does not qualify for a check claim. Its interval is positive; it is not an inconclusive interval.

Native findings from the separate fixed 30-pair workflows:

check: reduction 2.626168%; 99% interval [-7.532242, 11.428833]%; full wall-time gate not passed.
test: reduction -3.523362%; 99% interval [-18.706655, 9.478428]%; full wall-time gate not passed.

The first native admission stopped at its occupancy guard before fixture preparation or sampling. Its failed status, occupancy record, controller logs and complete launch history are retained with any reviewed recovery lineage. No observation from that admission is treated as a measurement. The metadata-only retention, byte-identical replay, additional quiet-guard rejection, accepted v2 lineage proof and root acceptance bridge before native raw review are retained with their exact approvals and execution streams.

Both native raw audits passed, and neither workflow established a native regression under the frozen rule. A wall-time claim is allowed only for a workflow that passes its full wall-time gate. Cargo-process Ir excludes rustc, linker, build-script children and kernel work. Instrumented elapsed time is not native timing.

Each pair contains one invocation per variant. Both phases have two additional warmup pairs. Inference uses paired log ratios, a 99% paired bootstrap with 20,000 resamples and seed 1701, an exact two-sided sign test, and separate AB/BA summaries. No observations, slow samples or failed attempts are dropped. No phases or historical binaries are pooled.

The first current179 IR attempt completed its 28 primary test records, then stopped before starting the check batch. A separately reviewed continuation retained those exact records and ran only the original missing fixed check plan. Its first launch stopped before new work because of an inherited PATH mismatch. That failure, the PATH-only launch correction, and the profiler-path alias review failure/correction are all retained. The completed groups were reviewed only after both raw workflow audits passed.

`raw/` contains the actual original archives, including every collected full Callgrind profile. A file larger than 90,000,000 bytes is preserved as ordered, lossless byte chunks; `RAW-MANIFEST.json` gives the exact reconstruction order and original hash. `lineage.tar.gz` retains the source, build, strip, correctness, approval, failed launch, alias and review records. `reviews/` and `summary.json` expose the accepted current179 results. `SHA256SUMS` binds the publication files.

Archives labelled `historical-pr175` are earlier selection evidence against a different parent and different binaries. They are retained separately and contribute no observations to the current179 estimates. See `REPRODUCE.md` and `VALIDATION.md` for the procedure and coverage limits.
