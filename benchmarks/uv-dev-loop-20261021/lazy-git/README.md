# uv warm dev-loop: defer Git initialization

Cargo registers its existing executable-only Git policy at startup and applies
it once before repository access. Certificate environment probing remains at
startup, and initialization is forced before HTTP/fix workers. Library owner
validation, HTTPS support, conditional git2-curl transport, and security policy
remain intact. The curl workaround checks its cheap conditions before looking
up a Git proxy. This removes unnecessary libgit2/TLS setup on fresh offline
commands that do not need Git.

The measured candidate source tree is `c692e3c07d295e596b9f10eb4b1c89bb498caf68`.
Baseline is PR175 (`efc8b51502f8a8d1fe76997dc984481edde2740e`) on pinned Cargo
`5e5d271d763d7beb38b48755e22bd59e93f02b97`. uv is unchanged at
`3d82a6ad5a7eab8c68236553b7846517767c4b61`.

| Fixed validation | Reduction | 99% paired interval | Sign p | Wins | Result |
| --- | ---: | ---: | ---: | ---: | --- |
| Warm check, Cargo instructions, 12 pairs | 3.9755% | 3.8356% to 4.0438% | 0.000488281 | 12/12 | Pass; both orders positive |
| Warm test --no-run, Cargo instructions, 12 pairs | 3.3892% | 3.3060% to 3.4341% | 0.000488281 | 12/12 | Pass; both orders positive |
| Warm check, native wall time, 30 groups | -0.0476% | -5.9726% to 5.0319% | 0.584664712 | 17/30 | Inconclusive; gate fails |
| Warm test --no-run, native wall time, 30 groups | 0.5755% | -1.8933% to 1.8039% | 0.000324914 | 25/30 | Inconclusive; gate fails |

Only the instruction reductions are claimed. Each instruction workflow passes
its own predeclared gate; neither was pooled with the other or with a screen.
Native groups contain eight calls and remain the statistical units. Native
test-build's small sign p does not override its below-threshold point estimate
and interval crossing zero. No native wall-time improvement or absence of
regression is established. No uv tests execute, and dirty rebuilds are outside
this workload.

The measured binaries use all-static/ohm-defaults, opt-level 3, ThinLTO, one
codegen unit and stock Rust 1.99.0. They have no PGO and are not the published
PGO toolchain. The workload compiler is pinned Ohm 1.99.0-6. Debug-only stripping
preserved allocated ELF sections. Callgrind 3.22 counts Cargo userspace
instructions only, excluding compiler, linker, build-script, test and kernel
work. Both variants encounter its brk/allocator fallback. Instrumented elapsed
time is not native time.

The final source passed 33 focused Rust tests and 12 SSL child-environment
cases, including library/CLI owner policy and existing HTTPS rejection/custom-CA
coverage. These correctness runs used normal/test-build binaries from the same
source, not the exact measured production CLI. The latter passed source,
build/strip, and fresh Ohm-enabled uv preflights. The initial invalid Once
Default derive and color-environment snapshot failure, their fixes and all
raw attempts remain visible. Cross-platform CI and a successful explicit proxy
CONNECT case are not covered. See [VALIDATION.md](VALIDATION.md).

Use [REPRODUCE.md](REPRODUCE.md), the frozen [protocols](protocols),
[runners](harness), [original configurations](configs), and
[build/source/strip provenance](build). Historical absolute paths are preserved;
seed new artifacts when reproducing at another prefix. [INPUTS.json](INPUTS.json)
maps recorded hashes to packaged metadata/source files and identifies external
runtime inputs. Executables are not included or made downloadable by their
historical local paths. Additional tool hashes collected while packaging are
explicitly labeled post-run.

[raw-results.tar.gz](raw-results.tar.gz) preserves every file from the four
completed result directories except the disclosed large Callgrind attribution
profiles, plus correctness logs/reports/captures, build logs and execve traces.
All raw samples, native subruns, warmups and preparations are included, including
both inconclusive native results. The profiles remain retained in the task
workspace; [counter extracts](callgrind-counter-extracts.jsonl) include every
profile's original hash, size and count, checked against the sample table.
[RAW-MANIFEST.json](RAW-MANIFEST.json) lists the archive contents exactly, and
[SHA256SUMS](SHA256SUMS) seals the package. Generated correctness-fixture targets
and cache databases are excluded. Historical review and freeze notes retain
their original pre-execution wording; completed validation reports supersede
their pending status.
