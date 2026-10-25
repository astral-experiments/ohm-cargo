# Five Cargo changes on the uv development loop

Published Cargo PRs #231 through #235 were built together with the same SDK12 producer as the unmodified Cargo revision `fdd26156`. Both binaries ran upstream uv at `3d82a6ad` with the same SDK. Each observation restored a warm workspace, changed five bytes in an ordinary source comment, and ran the build. The test compilation command used `--no-run`.

| Endpoint | Host 1, fewer Cargo instructions | Host 2, fewer Cargo instructions |
| --- | ---: | ---: |
| Dirty cargo check | 3.913% (99% interval 3.831–4.090%) | 3.977% (3.816–4.227%) |
| Dirty cargo test --no-run | 13.064% (12.953–13.143%) | 13.108% (12.920–13.270%) |

Each of the four host and endpoint combinations improved in eight of eight predetermined pairs, with a two-sided exact sign-test p value of 0.0078125. Each host has its own paired estimate and seeded interval. Counts cover the Cargo process. Compiler and linker work and elapsed time are outside this metric.

Run `python3 check/reproduce.py` and `python3 test-build/reproduce.py` from this directory to recompute the results from all 64 full profiles. Each endpoint includes the source patch, binary and build identities, prospective protocol, raw counts, and its own replay instructions.
