This is a bounded read-only capture and local boundary review for the native
inheritance attempt that failed at `driver.py:388` on 2026-10-21 at 16:18 UTC.
It does not contain a replacement benchmark driver or execute recovery.

The authenticated local traceback identifies the original quiet guard while
Python was evaluating `status.update(..., quiet=ref.quiet())`, before the first
preflight call. That preflight creates its metadata directory before installing
or running Cargo. The remote status, prerequisite and all native path absences
must still be captured and verified before declaring a zero-work boundary.

After independent source review, root may run this read-only capture:

```
taskset -c 8 /usr/bin/python3 -I -B work/inheritance-native-admission/collect.py \
  --source-freeze-sha256 CAPTURE_SOURCE_FREEZE_SHA \
  --output work/inheritance-native-admission/capture-01
```

The remote code reads 15 small metadata/control files, records the absence of
the ten native target/shared-cache/preflight/result/log paths, and verifies the
accepted 500-file IR inventory and original static seal by opaque hashes. It
retains the status and native prerequisite exactly. It excludes compiler/binary
payloads and existing IR profiles from the new transport; those bytes remain in
their original complete captures. It executes only the original read-only
asset/seal verification, with Git optional locks disabled for this collector.
It does not invoke the quiet guard, Cargo, any raw statistical audit, or analysis.

The capture is terminal evidence only and never qualifies the candidate. All
transport bytes and failures are retained in a new output. An unexpected native
path produces an unproven boundary and blocks recovery; no data is removed.

Then run the pure local review using the capture hash printed by the collector:

```
taskset -c 8 /usr/bin/python3 -I -B work/inheritance-native-admission/review_boundary.py \
  --source-freeze-sha256 CAPTURE_SOURCE_FREEZE_SHA \
  --capture work/inheritance-native-admission/capture-01 \
  --capture-sha256 CAPTURE_RECEIPT_SHA \
  --output work/inheritance-native-admission/boundary-review.json
```

Only if the actual review passes, the minimal prospective recovery is:

1. Independently bind this capture, its source review, the exact failed launch
   streams, and the boundary review. Require the original quiet guard to pass
   before any recovery mutation, with no ignored process or threshold change.
2. Recheck all original inputs, the 500 retained IR files, the exact failed
   status/prerequisite hashes, and the eleven absent paths. Require no owned
   measurement/controller process. If anything differs, stop and preserve it.
3. Create the previously absent owned remote namespace
   `metadata/native-admission-history/attempt-01`. Retain the source/review/capture
   bindings and all three failed local launch files there. Move only
   `results/native-status.json` and `metadata/native-prerequisite.json` into that
   namespace at their exact captured hashes. Preserve both bytes; record each
   move and the complete final inventory. A partial move must be inspected,
   never silently retried or interpreted as a completed recovery.
4. Retain/move only the three local `launch-native.{json,stdout,stderr}` files
   into a new exclusive local history directory. Keep their names/bytes and
   bind their original locations, hashes and relocation receipt. Leave the
   original launcher, driver, source freeze, seal, configs, fixtures and all
   prior IR/closure evidence unchanged.
5. Recheck input hashes and absence, then invoke the byte-identical original
   `stage.py --launch-phase native --sealed-inputs-sha256 b6e765…` once. Its
   original guards and fresh-fixture assertions still apply. Its new prerequisite
   rechecks already accepted IR files/gates; it does not rerun IR measurements
   or bootstrap analysis. Native remains the original two 30-pair × eight-call
   workflows, two warmup pairs, seeds 20261021113/114, with unchanged gates.

This is a zero-observation admission replay, not a replacement or extension of
native measurements. The existing collector automatically includes the remote
history namespace because it walks `metadata/`. Final collection/review must also
bind the preserved local failure and relocation receipt before any native claim.
There is no automatic retry and no authority to discard later observations.

The schema and source checks use only synthetic statuses and AST inspection.
Actual remote capture, recovery and native execution remain root-owned actions.
