# H5 run and data binding

Keep this protocol under a fixed H5 path separate from protocol-v3, protocol-v2 and ruff-evaluation-v2. The program expects the native H5 root /mnt/devbox-scratch/dev-user/ohm-combined-prs-20261028. The official SDK archive and each physical Cargo, rustc, driver and Wild digest are checked. The Cargo trace worker and its entire underlying protocol manifest are verified against the published v3 registration and unchanged v2 physical seed. This protocol never writes into those native-run directories. The stopped v1's first offline failure and zero-output receipt remain available through the v2 source registration.

First publish the wall plan and bind the source inputs. After both v3 selection phases finish using the completed v2 seed, place the following local inputs on the authorized host. No measured command may precede a successful, independently reviewed native admission.

1. Supply a qa.json with exactly these fields: source (the complete plan.json source object), observer and composed (actual SHA-256 of their Cargo binaries), status equal to pass, build, and tests. In build, the observer and composed records each contain cargo_sha256, recipe_sha256, profiles_sha256, source_recipe_sha256, evidence and receipt_sha256. The first two build recipe/profile hashes must match between arms. The evidence fields name actual files relative to qa.json, and the runner rereads those bytes against their SHA-256. These receipts must identify the real native toolchain builds and the source chains. A label or unverified GitHub head is insufficient.
2. Each of the test records built-library, unused, used, missing-proof, observer-replacement, ordinary-reader and cached-state-migration contains an actual receipt path in evidence, receipt_sha256, subject and exit. The first four must cover the source-identical composed Cargo including the checked-in scheduler regression. The observer safety and old-cache cases may use the verified #261 suite. Copy real receipts under qa.json's directory. Independent review checks that their contents actually show the stated source, commands, inputs and outcomes, and checks the exact PR CI status before issuing its grant. Native physical incidence, program outputs and the CI/test approvals are separate gates.
3. When all 110 raw digests match across every native run, no differences require adjudication. For a known or anticipated output that varies with linker width, supply wall-native-proofs/variants.json under the H5 root, keyed by the exact Cargo product path. Its value has a replays array, each with relative elf and receipt files and receipt_sha256. The referenced JSON must report target, exit=0, threads, actual elf_sha256, wild_sha256, same_verified_inputs=true, resolved_input_bytes_sha256, and argv_except_width_and_output_sha256. Independently review and retain the underlying real Wild argv and complete input digests. Bind only the width and private output path as differences. For each approved product, at least two worker widths of the same stock Wild, with identical actual resolved input bytes and equivalent options, must jointly reproduce every approved raw SHA-256. The actual saved first and repeat ELF files and forced outputs must match byte-for-byte except for the .rodata section's sh_entsize and the 32-byte GNU build ID payload. Keep the exact file names, digests, decoded widths, build IDs, and link inputs. No blanket per-section or per-host allowance applies. Even a byte variation attributable to one of those fields halts the study if its particular product/raw hash was not sealed before the first timed slot.
4. Run the admission and inspect its full record. It works only on the fixed host holding all native stores. No Cargo command is executed in this phase. It validates the CPU/storage controls, independent arm inputs, all 220 workspace and 156 registry first-selection ELF copies before repeat, both sets of repeat ELFs, the native gate and exact QA/build receipts. A native job-count miss or failed comparison ends this proposal. Review the original failure receipt in place; issuing a corrected plan is a separate decision. Publish and re-read the manifest of this plan and the native admission, then supply a distinct grant.json. The SHA-256 of the protocol SHA256SUMS and native admission, SHA-1 of both published Git revisions, scope, CI review, and host exclusivity are mandatory.

```sh
/usr/bin/python3 -IB runner.py admit /path/to/qa.json
# Only after an independent grant for these exact inputs
/usr/bin/python3 -IB runner.py score /path/to/grant.json
```

Grant fields are go equal to “score exact 24 pairs”, native_sha256, plan_manifest, published_plan, published_native, h5_clear equal to true, other_host_measurement equal to false, and ci_review equal to accepted. These two entry points refuse an existing result root. Once scoring begins, every successful raw clock, stdout/stderr, 110-workspace and 78-registry file maps, listing, unchanged Cargo JSON and exec trace remains in the uniquely named slot. An interrupted or invalid slot cannot resume or overwrite earlier timings. The external launcher should preserve terminal stdout, stderr and exit code. Only completed unfailed results can be analyzed.

The offline replay verifies all 48 starting/ending monotonic times in registered order, reconstructs each pair directly from its slots, checks all 2,640 cross-arm raw-file comparisons (plus both snapshots on each slot), verifies every warning, listing, fresh/dirty count and scored subject, and recomputes the exact test and interval. The unchanged phase's physical process list is also retained. The reference data and local assets may contain host-specific registry paths. Share reviewed portable aggregate products and hashes rather than general unfiltered host traces.

```sh
/usr/bin/python3 -IB verify_result.py /path/to/early-scheduler-wall-rc17-v1 /path/to/early-scheduler-wall-admission-v1.json
/usr/bin/python3 -IB analysis.py selftest
/usr/bin/python3 -IB check_guards.py
```

The generated-data check below exercises the complete 48-slot offline reader and corrupts one result to test its rejection. It runs no Cargo process. The schedule seed regenerates the published order exactly.

```sh
/usr/bin/python3 -IB check_result_reader.py
```
