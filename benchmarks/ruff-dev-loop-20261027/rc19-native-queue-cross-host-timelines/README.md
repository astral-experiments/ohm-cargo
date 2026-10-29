# Native link overlap on the two scheduling machines

Starting the largest ready links first improved the registered unchanged Ruff test-build endpoint on C5 by 7.58% and regressed it on H8 by 11.87%. The ordinary Cargo clocks determine that result. Separately, 12 stationary diagnostic builds per machine traced the complete process groups for the same 50 test links. The table gives medians across six unscored native invocations for each arm. Four additional C5 edit-series flanks are included separately in the data. [C5 wall result](https://github.com/astral-sh/ohm-cargo/tree/b028f6d2cabcd7c2806292c1f38b91493aa0f33c/benchmarks/ruff-dev-loop-20261027/rc19-native-queue-c5-wall-results) · [H8 wall result](https://github.com/astral-sh/ohm-cargo/tree/7957cc89f9ebc5fcef31e963b0606854fd86cd1a/benchmarks/ruff-dev-loop-20261027/rc19-native-queue-h8-wall-results)

| Stationary native diagnostic | C5 default | C5 largest first | H8 default | H8 largest first |
| --- | ---: | ---: | ---: | ---: |
| Start of ty_server e2e relative to the first Wild | 4.090 s | 0.045 s | 2.073 s | 0.036 s |
| Last Wild launch to last Wild exit | 7.943 s | 4.138 s | 0.762 s | 0.023 s |
| Pairwise overlap among the ten largest native links | 25.38 pair-seconds | 45.34 pair-seconds | 9.34 pair-seconds | 23.02 pair-seconds |
| Peak sum of ongoing links’ output sizes | 1.368 GB | 1.584 GB | 1.363 GB | 1.584 GB |
| Sum of service times for the ten largest links | 26.16 s | 28.24 s | 9.54 s | 10.23 s |
| First Wild launch to last Wild exit | 16.03 s | 18.30 s | 5.08 s | 4.36 s |
| Last rustc exit to Cargo exit | 0.230 s | 0.140 s | 0.415 s | 1.343 s |

Both machines launched the large e2e target earlier and ran more large linkers concurrently. The shorter tail after the last native launch occurred on both hosts. The directions of the full Wild interval and of the subsequent Cargo interval differed between machines. These are traced process-parent intervals; they include launch and scheduling effects, and Wild children can finish cleanup after the parent exits. The observations cannot distinguish storage throughput, processor contention, jobserver behavior or other host differences as the cause of the opposite end-to-end results. A universal scheduler change failed its registered gate.

The final C5 restoration also left seven targets with different temporary Rust object names in the subsequent off-clock link commands. All 456 physical file pairs, totalling 33,492,416 bytes per arm, matched in full content and size. The 1,368 changed native argument positions span GCC, collect2 and stock Wild. Complete per-target current name slots, inode commitments, saved link state and manifests are verified in `restored-inputs`. Neither these delayed reads nor the size inventory at an earlier native command are measurements of a linker’s exact input-acquisition instant.

Run `sha256sum -c SHA256SUMS`, `python3 -IB analyze.py`, `python3 -IB c5/verify.py`, and `python3 -IB restored-inputs/verify.py`. The common program computes all 1,400 physical intervals across 28 diagnostic commands. Both machines retain their original timings and per-trace SHA-256 commitments. [Original H8 mechanism](https://github.com/astral-sh/ohm-cargo/tree/bcf8bbcf6ea6207d6d31d0cd7693a90f7136074f/benchmarks/ruff-dev-loop-20261027/rc19-native-queue-h8-mechanism)
