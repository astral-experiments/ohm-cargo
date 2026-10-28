# H5 wall operator for Cargo #260 and #261

These three scripts run from the coordinator’s existing `rc17-composed-early-test-ops` directory alongside its private receipts. Their sealed copies here are identical. The v3c source installation is complete. H5 recorded 46 installed files, including the manifest. Its unattempted v3b predecessor has 40. Both launchers preserve the original job manager with SHA-256 `acf1088fd8dab3b2c06f6be9b6ed35c2f0c3649b8a9a2b671b5f5d1e0ec2c614`. They write each role’s own ordinary stdout, stderr and unmodified exit code. [Active wall source](https://github.com/astral-sh/ohm-cargo/tree/f8ee28c60e872a090b4600f473b303738be05029/benchmarks/ruff-dev-loop-20261027/rc17-composed-early-wall-plan-v3c) · [Native bootstrap](https://github.com/astral-sh/ohm-cargo/tree/4de32538d02e25b5c8f75e58eea48c9b55fd0445/benchmarks/ruff-dev-loop-20261027/rc17-composed-all-links-bootstrap)

## Native review and admission

After the independent native result and reviewer’s witness are published and read back, add the exact result component and Git commit to the coordinator’s existing publication map. Use the actual reviewer filename and the actual native verifier receipt filename. The physical reread must use the registered original verifier and match the independently published source `root-native-reread.py` (SHA-256 ec0d86f448c442168b7407fff3814a9b1cdfe05d26b77795f7c80467f191b758). It must reopen 9,867 stock processes, including 9,568 explicit runs and 299 ordinary controls, and reproduce all 53 byte commitments. The review JSON contains `independent_review` equal to `accepted`, `workspace_linked_targets` 50, `fresh_occurrences` 297, `registry_exact` 78, `historical_native_ref` a75e5f17c07081cfcc9fabfcccd7a5022528641b and `view_sha256`, `terminal_sha256`, `verifier_receipt_sha256`. The host requires those three hashes to match its real native records. Preserve the original verifier under its physical H5 filename. The published verifier may use another relative filename when it contains the same bytes.

From the existing coordinator ops directory, run the following one step at a time with the root operator’s authorization.

```sh
python3 -IB prepare-wall-v3c.py catalog "$NATIVE_RESULT_COMPONENT" "$ROOT_WITNESS_FILE" --verifier-file "$VERIFIER_RECEIPT"
python3 -IB route-wall-v3c.py bind-catalog
python3 -IB route-wall-v3c.py admit
# Wait for admit.exit. If it failed, record the first error and use the terminal exporter.
python3 -IB route-wall-v3c.py admission
python3 -IB prepare-wall-v3c.py seal
```

The admission component is `rc17-composed-wall-admission-v3c`. It contains the exact original launch `ci.json`, `catalog-publication.json` and `admission.json`, seven files from the native publication or registered bootstrap and `provenance.json`. It also includes the independent CI check and source binding. The wire format carries the exact bytes of each of the eleven launch files and its SHA-256. Reformatting the JSON changes its identity.

## Separate operator release

Publish and independently read back the zero-clock H5 admission before issuing a grant. After the H2 scheduler study finishes, the H2 operator issues a second, new receipt named `wall-v3c-h2-released.json` in the coordinator ops directory. The file must have exactly these fields.

| Field | Required value |
| --- | --- |
| study, study_ref | `rc17-text-size-first-selection-wall-plan` and `44c3e6db80242b5461bbb3f86f2fae5a0f166a45` |
| host | `charlie-ohm-relink-b-1024` |
| status, score_exit | `complete` with 0 or `failed` with a nonzero integer |
| terminal_component, terminal_ref | Actual independently published component and its immutable commit in the coordinator’s map |
| terminal_file, terminal_sha256 | Published relative terminal marker and its exact SHA-256. A completed marker declares `phase=all_slots_finished` and `slots=48`. A failed marker is a nonempty `failure.txt`. |
| ended_unix_ns, released_unix_ns | Positive integer epoch nanoseconds with end at or before release |
| released_for, admission_sha256 | `f8ee28c60e872a090b4600f473b303738be05029` and the exact local/public H5 admission digest |
| scored_processes_running, owner_review | 0 and `released by H2 operator after terminal` |

The H2 reader checks `host-receipts.json` from the same immutable result component. The score process must have the reported exit and end time. The admission and verifier must both exit zero and the manual release must follow the physical verifier’s timestamp. It authenticates all three role exit digests. The observed H2 result commit is `05ed34e5bda78680b9089d4efd7acf32c3fa3d82`, manifest `52048aff352be1d00396d037c9cc1c82af7d8d7f857a0a0b3a9451dc532c9f05`. The coordinator independently read `terminal.json` and `host-receipts.json`; the manual H5 release is still required. The local prepare script loads the sealed sibling exporter’s `sideproof.py` for these two independent checks.

The H5 operator separately writes `wall-v3c-lanes.json` containing `host` equal to `charlie-ohm-c5-check-1025`, `other_scored_processes` equal to 0, a nonempty `owner_review`, current `unix_ns`, `admission_sha256` and `h2_release_sha256` for the unmodified H2 release file. Its time must be at or after H2’s release.

```sh
python3 -IB route-wall-v3c.py idle
python3 -IB prepare-wall-v3c.py grant
python3 -IB route-wall-v3c.py score
# After score.exit is 0, complete.json exists and there is a separate verification role to run
python3 -IB route-wall-v3c.py verify verify_result.py
```

Both the idle sample and H5 approval must be less than 180 seconds old at dispatch. The dispatcher rechecks CI, both current heads, the entire published admission, the separate H2 release, the H5 lock and the processes immediately before launch. The literal grant is `score exact v3c 24 fresh pairs`. The final verifier filename can select only a file from the registered plan with the exact original verifier bytes. A nonzero admission, score or verifier exit is retained. The terminal exporter can report any such failure. The independent score allocation and analysis are in the wall plan. 

## Local tests

```sh
python3 -IB check-operator.py "$POSITION_INTEGRATED"
sha256sum --check --quiet SHA256SUMS
```

The operator test locally runs the install and byte-transport branches in a temporary directory, checks rejection of an earlier attempted wall, a duplicate installation and a repeated job, then checks both allowed H2 terminal shapes and invalid owner, time, Git ref, output and CI. It opens no actual H2/H5 result or wall clock.
