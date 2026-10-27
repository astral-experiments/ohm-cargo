# Whole Ruff workspace check after a build-script edit

This trial uses Ruff 93526150df and the entire three-script historical change a8ba9e0458 in both directions. The control Cargo source was d38fdd0250 and the fix was 6b1cdb8925. Both release-profile PGO builds used the same pinned LLVM packaging and #233 compiler. The control was rebuilt independently and the two packaged executables matched byte for byte. A separate cohort measures the Cargo revision distributed in Ohm 1.99.0-16.

Each of 24 ordered pairs contained two whole-command episodes from separately copied, fully fresh snapshots. Twelve pairs reversed the patch, twelve restored it, and each direction had six episodes with the control first. Each arm timed the edited check followed by two untouched checks. Traced commands were outside the measured window. The registered inference uses exact order randomization, direction-stratified paired bootstrap intervals, and Holm adjustment across three primary endpoints.

| Endpoint | Control median | Fix median | Paired reduction (95% interval) | Holm p |
| --- | ---: | ---: | ---: | ---: |
| Changed check | 1.382 s | 1.411 s | −0.97% [−6.05%, 4.08%] | .701 |
| First untouched check | 1.035 s | 0.597 s | 39.67% [35.32%, 43.65%] | .00000703 |
| Changed plus first untouched | 2.436 s | 2.094 s | 16.08% [12.64%, 19.62%] | .0000141 |

On both edit and restoration, each Cargo ran the three real build scripts, eight full compiler invocations and three Wild links. On each following untouched check the control launched three compilers, reporting 514/520 fresh. The fix reported 520/520 fresh with no rustc or Wild process. All 24 untouched pairs and 23/24 two-command sums took less wall time with the fix. The second untouched check was descriptive. The changed check alone did not pass the registered threshold. The measurements concern workspace checks. They do not estimate native build or test-build timings.

Run `python3 -B verify.py` to reproduce the arithmetic and verify the 144 monotonic readings. Each command's units, raw clock and output digests, as well as typed qualification and final traces, are in `raw.tar.gz`. The earlier calibration publishes the full external-input and generated-output controls.

[Registered study](https://github.com/astral-sh/ohm-cargo/tree/30c4bfb6a1989da3818a2381b6cd46cd39c0e50e/benchmarks/ruff-dev-loop-20261027/build-script-timestamp-timing-plan) · [Release and replay binding](https://github.com/astral-sh/ohm-cargo/tree/48315db20888818962111bad4e758f246a9b9a37/benchmarks/ruff-dev-loop-20261027/build-script-timestamp-release-binding)
