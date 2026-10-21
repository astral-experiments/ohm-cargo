This is a local, source-only evidence packager. Neither prepare_inputs.py nor
assemble.py has run on the real native phase. The thirteen synthetic checks use
temporary fixtures only. No helper imports a host client, runs a subprocess,
invokes Cargo, samples a workload, or computes statistics.

Wait for the original fixed native phase to finish and for the approved native
admission wrapper to produce its accepted terminal review. The expected review
directory is `work/inheritance-raw-review/native-admission-closed`; its unchanged
phase review lives in `phase/review.json`. Both IR gates must pass. Native may
remain a valid negative, but a significant native regression stops packaging.

After source review and those terminal prerequisites, use:

```
taskset -c 8 /usr/bin/python3 -I -B work/inheritance-evidence-preparation/prepare_inputs.py \
  --native-review-sha256 ACCEPTED_NATIVE_PHASE_REVIEW_SHA \
  --native-transfer-manifest-sha256 FINAL_NATIVE_TRANSFER_MANIFEST_SHA
```

This creates a new `final-inputs/` directory containing the final documentation
and an exact inputs.json. Review that manifest and its SHA before assembly:

```
taskset -c 8 /usr/bin/python3 -I -B work/inheritance-evidence-preparation/assemble.py \
  --inputs work/inheritance-evidence-preparation/final-inputs/inputs.json \
  --inputs-sha256 REVIEWED_INPUT_MANIFEST_SHA
```

The output is the previously reserved, initially absent
`work/pr-evidence/workspace-inheritance-stack180`, with an adjacent publisher
manifest. Neither script publishes anything.

The assembler rechecks complete capture membership and original tar contents,
both independent phase reviews, fixed counts/seeds, accepted IR identity, native
admission-before-effects and final-review joins, the transport closure, exact
source/CI identities, and no significant native regression before creating the
package. It retains the actual failed IR, closed IR and final native payload.tar
bytes inside a deterministic lossless gzip archive. Full Callgrind profiles and
all collected envelopes remain present. Local source reviews, failed launch
receipts, recovery controls, exact metadata relocations and replay approval are
included, along with matched build/strip provenance and correctness records.

The runtime/executable staging payload, compiler-build tree and two production
executables are not duplicated. Their existing identities and complete build,
runtime and setup metadata remain. These are distinct from every raw measurement
archive, which is retained without omission. The archive stops at the 100 MB
Git-blob boundary for an explicit lossless split if necessary. No observations
are dropped to meet that bound.

RAW-MANIFEST.json records each original archive, every remote and envelope member,
all local lineage inputs, and the exact outer archive members. Assembly rereads
the completed outer archive and rehashes every source input before writing the
publication manifest and SHA256SUMS. A failed assembly is retained; no output is
silently replaced.
