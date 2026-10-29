# Direct release EH study

## Completed edited uv test builds

After an edit to uv, Cargo, rustc and Wild together executed 0.167% and 0.155% fewer instructions on two independent checkouts than with the Wild binary in Ohm -18. Each checkout ran `cargo test --no-run --locked --offline -j8`. All eight paired runs improved in each comparison.

Wild writes an unwind header entry for each frame description entry. Its two checked offset conversions now use the inline success path in `with_context`. The relocation writer also borrows the same empty cache and instruction map throughout an input section. The overflow diagnostics remain byte-identical in the malformed fixtures.

The table gives median paired instruction reductions. Parentheses show exact 99.22% intervals for the median. Each command ran one Cargo, six rustc processes and five Wild processes, and produced 72 test executables.

| Checkout | Linker used for comparison | Cargo, rustc and Wild | Wild only |
| --- | --- | ---: | ---: |
| First | Source-matched Wild | 0.196% (0.085–0.336%) | 0.462% |
| First | Shipped -18 Wild | 0.167% (0.039–0.296%) | 0.398% |
| Second | Source-matched Wild | 0.248% (0.085–0.320%) | 0.594% |
| Second | Shipped -18 Wild | 0.155% (0.044–0.189%) | 0.407% |

The edits change a predicate in `crates/uv/src/install_source.rs` using separately assigned literals. Across the four comparisons, 2,336 of 2,368 artifact comparisons were byte-identical. The other 32 differed only in a section-header field and its build ID, the same variation observed when replaying the shipped linker against itself. The native runs verified the processes and artifacts. The scored runs counted instructions with DynamoRIO.

The two-sided paired sign test gave 0.0078125 per row and the balanced-order test gave 0.0285714. [Download the registered protocol, raw counts, artifact receipts and offline verifier](complete-command.zip). Archive SHA-256 `07f0710d0f7d6122396f06b71b107f8bdedb14a34fa0786a3c53e1e179427a19`.

Unpack the archive and run `python3 -I -B command-v2/verify-complete.py` from its root.

`eh.patch` changes only `libwild/src/elf_writer.rs` on `e856d81f6683cad80b9fe0ebf1a0c3c403c6fe11`. The fully patched file under `source/`, its SHA-256 and the exact base source/lockfile IDs under `source.json` can be checked without building. `plan.json` SHA-256 is `831b24ff4991229569294e4a73d06b872b762628104592aa54b36601d56f2c6f`. The full-command plan on the retired older #46 never ran.

After a non-native build/counting allocation, write its timestamp, exact released logical CPUs and permitted task labels to a private allocation JSON. The study labels are `current-pr46` and `release-eh`. The shared build script requires its own affinity to equal the recorded allocation. It builds current #46 first when requested. It then builds the released source control and treatment from the same source path. It rejects a changed baseline hash and preserves the distributed Wild as a third executable. Its standard Cargo driver is rustc/Cargo 1.99.1 with the matched release profile and lockfile.

```sh
taskset -c "$ALLOCATED_CPUS" python3 work/round18-linker/build-anchored.py current-pr46 --allocation "$ALLOCATION"
taskset -c "$ALLOCATED_CPUS" python3 work/round18-linker/build-anchored.py release-eh --allocation "$ALLOCATION"
taskset -c "$ALLOCATED_CPUS" python3 work/round18-eh-release/lock-focused.py --allocation "$ALLOCATION"
taskset -c "$ALLOCATED_CPUS" python3 work/round18-eh-release/official-tests.py
taskset -c "$ALLOCATED_CPUS" python3 work/round18-eh-release/fixtures.py
taskset -c "$ONE_ALLOCATED_CPU" python3 work/round18-eh-release/focus.py
```

The gate records uncensored raw counter and diagnostic streams per arm, exact input/output identities and portable paired statistics. The conditional complete-command experiment requires both controls on both actual link captures, the correctness gate, its own input/collector lock and a further explicit eight-CPU allocation. Each complete command is the actual edited uv test build, with all Cargo/rustc/Wild instructions and output bytes validated. Its native admissibility cells audit process and product coverage and supply no wall-time result.
