# Independent inheritance evidence review

This reviewer operates on local, completed collections only. It imports neither
the experiment controller nor its statistical harness, contacts no host, and
executes no Cargo command. All new output goes to a new review directory.

The experiment identity is fixed to source freeze `f52a57b6...`, measurement
seal `b6e76505...`, uv `3d82a6ad...`, and the fresh production pair `3164f928...`
versus `3b1a2e4e...`. Earlier binaries and observations cannot enter a review.
The exact full identifiers are literals in `evidence.py` and the final receipts.

`setup-review.json` records the completed independent setup audit. Its first
launcher failure, before input reads, is retained in
`setup-review-attempt01.json`. Use the isolated system interpreter below to
avoid the shell's Python missing-import hook.

## Source and setup checks

`evidence.py` authenticates the source freeze, production cohort/build/strip
records, source trees, correctness and CI prerequisites, complete transfer
archive, extracted bytes, and the exact configuration derivation. Existing
base `record_files` are retained in their original order before deduplicated
additions. Every present ancestor configuration is bound, including the exact
global `/.cargo/config.toml` observation. The remote seal and audited delivery
bind excluded compiler/tool/binary payloads; the reviewer does not fetch them.

The experiment collector accepts completed phases only. A failed or interrupted
phase therefore needs a separate read-only preservation capture from the root
agent. Such an attempt must remain retained and cannot be labelled passed by
this reviewer. Neither collection nor review is a permission to retry a phase.

## Fixed-phase review

Run these commands **only after root explicitly reports that the corresponding
fixed phase is terminal and its collection has completed**. The explicit
`--analyze-after-terminal` flag is required for statistics. Without it, the
reviewer checks both raw workflows and emits `raw-verified`, with
`qualifies: false`; it does not calculate effects. Never reuse an output name.

From the task workspace:

```sh
taskset -c 8 /usr/bin/python3 -I -B work/inheritance-raw-review/review.py \
  --controls work/inheritance-measurement --phase ir \
  --output work/inheritance-raw-review/ir-review-01 --analyze-after-terminal
```

The IR phase is 12 fixed pairs plus two warmup pairs per workflow, seeds
20261021111 and 20261021112. All 28 samples per workflow, every raw Callgrind
profile, prepare/timed logs, JSON/JSONL/CSV rows, canonical binary identity,
recorded inputs, and exact balanced AB/BA plans must pass before either
workflow's analysis file is parsed or its effect calculated.

Only if both IR gates qualified, the separately collected native phase can be
reviewed with the accepted independent IR receipt:

```sh
taskset -c 8 /usr/bin/python3 -I -B work/inheritance-raw-review/review.py \
  --controls work/inheritance-measurement --phase native \
  --ir-review work/inheritance-raw-review/ir-review-01/review.json \
  --output work/inheritance-raw-review/native-review-01 --analyze-after-terminal
```

Native uses 30 fixed pairs of eight separately timed Cargo calls plus two
warmup pairs, seeds 20261021113 and 20261021114. Each workflow contains 64
groups and 512 calls, of which 480 calls belong to the 30 measured group pairs.
The reviewer joins the separate subrun tables with nested repetitions, checks
all integer and CPU sums, exact call identities and combined log bytes, and
binds the prerequisite to the unchanged accepted IR evidence. It never pools
IR or earlier native observations with these 30 pairs.

Both phases retain exactly three untimed setup calls per variant, followed by
zero-child exec traces and cross-switch freshness checks. Prepare and timed
stderr must contain `Finished` without `Checking`, `Compiling`, `Running`, or
error signatures. Commands must be the frozen `check` or `test --no-run`
commands; no uv tests execute. Initial setup calls may compile the fixtures.

`raw-integrity.json` is written only after both workflows pass, before effect
analysis. The final review independently reconstructs the complete retained
analysis (including CPU and descriptive repetition summaries), paired log-ratio
bootstrap with 20,000 draws, seed 1701 and 99% interval, exact two-sided sign
test excluding ties, and separate AB/BA effects. Native inference uses 30 pair
aggregates; repetitions are never treated as independent samples. All raw bytes
and reviewer sources are rehashed after successful statistical review.

The phase gate requires at least 1% reduction, a positive 99% lower bound,
sign p at most .01, and positive point effects in both orders. A review returns
`passed` only if both fixed workflow gates pass. `valid-negative` means the
raw observations and calculations are valid but one or both gates fail;
`qualifies` remains false. `invalid` means an input/integrity/statistical
comparison failed. Exit code zero includes valid negative evidence; consumers
must read the explicit decision fields. Native regression is separately
identified by an entirely negative 99% interval and sign p at most .01. A
native gate failure alone does not establish a regression.

The metrics have distinct scope. Callgrind `Ir` counts Cargo instructions only
(`--trace-children=no`); its elapsed times do not support native wall-time
claims. Native data describe this warm, already-built dev loop, not a dirty
rebuild or test execution. The matched production-settings binaries omit PGO
and are not a claim about an independently bootstrapped release toolchain.

No statistics or measurement data have been executed by this reviewer at its
initial source freeze. The setup audit and source/AST checks are the only
executed checks at that point.
