# Direct release EH study

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
