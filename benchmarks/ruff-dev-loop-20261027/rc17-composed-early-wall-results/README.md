# First full Ruff test selection stopped at its native output check

The preregistered 24-pair trial stopped in block 2, slot 2, on Cargo #261 alone. Its timed first selection returned success and all 110 workspace ELF hashes and 78 registry ELF hashes passed. The ordinary unchanged follow-up then returned success, with 563 of 619 Cargo units fresh. It ran a full ron compiler, 50 link-only rustcs and 50 actual Wild invocations. Two of its 110 workspace ELF hashes were outside the set fixed before timing. The 78 registry products still matched. The retained state independently reproduced all 188 follow-up file hashes. [Protocol](https://github.com/astral-sh/ohm-cargo/tree/3a7bba8da2347af0ee04f847ddc786e7be3783f2/benchmarks/ruff-dev-loop-20261027/rc17-composed-early-wall-plan-v2) · [Pre-timing admission](https://github.com/astral-sh/ohm-cargo/tree/bd7280e6aa38f26f48181d4c26a75f1508985203/benchmarks/ruff-dev-loop-20261027/rc17-composed-wall-admission-v2)

| Test executable | Admitted SHA-256 prefix on first selection | Untimed follow-up and retained SHA-256 prefix | Retained bytes |
| --- | --- | --- | ---: |
| ruff_python_formatter-519c0544e58f942c | 88aca52cf9db0204 | f56d2f9441e7bae5 | 36,947,872 |
| ty_project-30613778192a6cff | 2cd957cc60a4a644 | a2c3105ef595009e | 194,127,680 |

The record contains all four completed ordinary clocks, three verified slots, one completed pair and the first native-output exception. The scoring runner exited 1. The complete-series verifier did not run. No effect estimate, confidence interval or p-value was computed. The earlier untimed process counts reducing 4 full compilers to 3 and 51 links to 50 on first selection remain separate from this stopped timing trial. The earlier v1 admission had stopped at an XFS requirement with zero clocks. [Independent native process and product evidence](https://github.com/astral-sh/ohm-cargo/tree/a75e5f17c07081cfcc9fabfcccd7a5022528641b/benchmarks/ruff-dev-loop-20261027/rc17-composed-early-native-results)

The two unregistered hashes explain the stop. This evidence does not identify the differing bytes or their cause. Both executables were physically linked on that untimed follow-up, and its 200-test discovery listing matched admission. No test bodies ran. All original ordinary stderr and first exceptions are available in the packet. Private follow-up exec argv and Cargo JSON records have file-level and per-process commitments with safe typed projections.

## Offline verification

The independent read on the original host produced a single 327,806-byte results.json.gz. The producer and receiver agreed on the full SHA-256, 6b53d6de8973d5e55a3f294980901e9dde9ef64de26685a8f98e63db9860ea7d. Extract the previously published wall protocol and native result directories beside this directory, under the names below. The executable reader only inspects the original recorded output.

```sh
sha256sum --quiet -c SHA256SUMS
/usr/bin/python3 -IB tools/verify.py results.json.gz ../rc17-composed-early-wall-plan-v2 ../rc17-composed-early-native-results | diff -u verified.json -
/usr/bin/python3 -IB recheck.py | diff -u stopped.json -
```

The first command checks the result and reader bytes against the supplied SHA-256 manifest. The second compares the original arm assignment and all recorded progress with the registered plan and independently published input and output commitments. The last check reproduces the exact first exception, both retained-file digests, the real follow-up process roster and the registry comparisons. The tools directory preserves the terminal exporter, its source seal, its successful complete-series and failure-path synthetic checks, and the original stopped v1 storage receipt.
