# H2 handoff

Use the following fixed paths on charlie-ohm-relink-b-1024.

~~~sh
R=/dev/shm/ohm-text-size-first-selection-20261028
W=$R/wall-protocol-v1
L=$R/wall-launch-v1
A=$R/wall-admission-v1
S=$R/wall-result-v1
~~~

Install the published flat source under W after checking every SHA256SUMS entry against the public commit. The registered authority in R/protocol, literal source path, original seed, four native selections and installed release stay in place. The shared host lock is `/mnt/devbox-scratch/dev-user/ohm-whole-skips-20261027/native-measure.lock`. The role manager creates separate logs, terminal exit files and count-only status under L. The worker requires new admission and result directories and creates them itself.

1. Write L/registration.json with exactly `wall_ref`, `wall_sha256`, `native_result_ref`, `native_result_sha256`, `native_plan_ref` and `native_plan_sha256`. The wall ref identifies the new public source and its digest is SHA-256 of the installed SHA256SUMS bytes. Copy both native refs and manifest digests from plan.json. Write L/ci-current.json with a fresh read of the exact heads and the two-PR GitHub check schema in ci-exact-heads.json.
2. Run `/usr/bin/python3 -IB "$W/runner.py" admit`. Success produces A/admission.json and two verified unclocked slots. Export `/usr/bin/python3 -IB "$W/portable.py" admission "$A" > admission.json.gz`. Repeat `python3 -IB "$W/portable.py" verify admission.json.gz` off-host. Publish the result before granting wall time.
3. Write L/grant.json with precisely `action` = `score exact H2 24 fresh text-size pairs`, `admission_ref` (separate published preflight), `admission_sha256` (the exact bytes of A/admission.json), and the existing `native_result_ref`, `wall_ref` and `wall_sha256` values. Execute `/usr/bin/python3 -IB "$W/runner.py" score` once, retaining stdout, stderr and terminal status. During the run, count verified.json files or existing slot directories. Release clocks, Cargo stderr containing its own elapsed display, and effect analysis after the process has exited.
4. Execute `/usr/bin/python3 -IB "$W/verify.py" "$S" "$A"` on H2 after terminal. A complete run validates raw per-PID trace bytes, parsed Cargo rows, process clocks and the final result. A failing run reports its first exception digest and retains the slot data without a partial effect or p-value. Export `/usr/bin/python3 -IB "$W/portable.py" result "$S" "$A" > result.json.gz`. Off-host `python3 -IB "$W/portable.py" verify result.json.gz` checks the paired calculations and public commitments. Include the actual manager exits separately. Retain the raw H2 data, including the first failed ordinary output, if applicable.

Portable packets include the original clocks and successful ordinary stdout/stderr, each declared file’s SHA-256, size and kind, the raw four listings, the 11 typed row hashes, the repeat inventory and the SHA-256 of every original per-slot receipt and trace. The private reader parses raw Cargo events and strace files. The portable reader checks their original digest commitments, coverage and sanitized projections. General process argv and private source registry events stay in the original H2 evidence. An unsuccessful packet retains recorded clocks, the first exception commitment, measured-path output differences and the hashes of retained small files.

For local review, `python3 -IB selftest.py` constructs and rereads all 48 synthetic slots, the two unclocked preflights, a failed slot and deliberately corrupted artifacts. `python3 -IB statistics_controls.py` distinguishes the numerical cutoffs on generated pairs. Neither exercise executes a compiler, linker or timed Cargo command.
