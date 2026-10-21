The remote inheritance IR metadata closure completed even though its SSH
transport returned 255. This directory contains collection and review adapters
only. It provides no launcher or mechanism to run the closure again.

The failed local launch remains `launch-finalize.json` (SHA `17e73463…`), with
its empty remote stdout and exact SSH error stderr. The wrapper attempt remains
failed (`retry/attempt.json`, SHA `c9309db4…`). The first pre-staging failure
remains in the original sibling package and in `retry/history/`. Nothing is reset
or relabelled as a successful process exit.

Root's later read-only inspection (`retry/root-after-transport-inspection.json`,
SHA `e67d84f2…`) found completed remote finalization `23553c50…`, completed IR
status `733cc2e9…`, the started receipt, and all six analysis/output files. It
recorded their hashes without inspecting effects. The finalization finished
after the local SSH transport ended, so the new chronology joins completion to
that later inspection. The remote process exit code remains unavailable; the
claim is completion of the frozen metadata closure, supported by its receipt,
full preserved raw/input bytes, exact analysis tail, output hashes and both
integrity checks.

The original 47 closure source files, capsule/source freezes, original driver,
quiet guard, raw observations and statistical code remain unchanged. The new
collector changes only local path selection, this exact transport outcome, and
additional history collection. Its embedded remote collector is byte-identical
to the reviewed collector. The lineage adapter retains every existing capsule,
source, 477-file raw-preservation, repeated-integrity and analysis-command check.
It replaces the unavailable successful stdout/exit-0 join with the authenticated
failed transport and later read-only completion/output bindings.

After source review, root may collect the existing completed phase:

```sh
taskset -c 8 /usr/bin/python3 -I -B work/inheritance-ir-closure-retry/transport/collect.py \
  --phase ir \
  --source-freeze-sha256 befbcd80ecdbfa09a14a39faf11891a01b65cb544522417fbbc29b3aa4352d10 \
  --transport-source-freeze-sha256 TRANSPORT_FREEZE_SHA256
```

The original transport archive, manifest and receipt are retained as produced.
Separate `local-transport-resolution/`, `transport-resolution-manifest.json`,
`transport-resolution.tar` and archive-descriptor files bind all frozen controls,
both failed local closure histories, the absence proof and the later inspection.
The original failed IR capture also remains retained and verified.

The review wrapper loads the byte-identical original evidence, raw and statistics
modules with the new, explicitly recorded lineage adapter. Both raw workflows
still pass integrity before any effects are inspected. Statistics are enabled
only by the existing explicit terminal-phase flag:

```sh
taskset -c 8 /usr/bin/python3 -I -B work/inheritance-ir-closure-retry/transport/review.py \
  --phase ir --output work/inheritance-raw-review/ir-transport-closed \
  --transport-source-freeze-sha256 TRANSPORT_FREEZE_SHA256 --analyze-after-terminal
```

The original `review.json` reports the original raw/statistical result; separate
`transport-resolution-review.json` records the effective adapter and failed
transport lineage. Valid negative gates remain nonqualifying. If both IR gates
pass, the already frozen native phase is unchanged. Its later collector uses
`--phase native`; its reviewer also supplies the qualifying IR `review.json`,
and checks the matching transport-resolution review. No observations are added,
replaced or pooled, and no remote analysis is repeated.
