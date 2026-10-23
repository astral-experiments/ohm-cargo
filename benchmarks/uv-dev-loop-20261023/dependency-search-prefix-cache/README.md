# Reusing dependency search-path prefixes

This evidence package concerns one Cargo change: reuse the sorted dependency `-L` prefix when prepared commands have the same ordered direct dependency Units. The measured candidate is `b88fc34856f083af4f51fe1703e6d106a02dc01d`. The [published source](https://github.com/astral-sh/ohm-cargo/commit/3d4b75624dad522994ff0fbede55b86d095e342e) is `3d4b75624dad522994ff0fbede55b86d095e342e`; its full tree `fd326f2a34a65f87a08a78202926739057788821` and sole parent `cfd816c7abd23ab589fd1cbc9c066eba314a8016` exactly match the measured source. Commit metadata differs; the measured identity is retained separately.

Two independently audited fresh confirmation blocks reduced **Cargo-parent guest instructions by 12.420256% and 12.347608% geometrically** on a controlled dirty uv test-build. Both separately passed the fixed eight-pair instruction gates. This metric excludes compiler/linker instructions and kernel work.

**Native wall sanity did not demonstrate a win:** the candidate’s geometric point estimate was **3.834912% slower**, with losses in **4/8 pairs**. The predeclared blocker required both at least 3% slowdown and at least six losses, so it did not trigger. This is a valid but inconclusive, mixed native result; neither a wall gain nor absence of native regression is established. All 36 strict quiet checks passed, and there is no extension or rerun.

| Stage | Accepted data in this draft | Decision |
| --- | --- | --- |
| Discovery | AB: 1,882,868,223 → 1,649,139,508 Ir; BA: 1,882,915,265 → 1,649,275,397 Ir | Both positive; fixed 5% advance gate passes |
| Check sanity | One AB pair: 3,033,154,558 → 3,025,815,963 Ir | Fixed regression guard passes; no check-gain claim |
| Confirmation block 1 | 12.420256% Cargo Ir reduction; 99% interval [12.380324%, 12.488040%]; 8/8 improve | Its fixed gate passes |
| Native wall sanity | Candidate +3.834912% geometric wall; 4/8 losses | Mixed/inconclusive; fixed AND blocker not triggered |
| Confirmation block 2 | 12.347608% Cargo Ir reduction; 99% interval [12.207287%, 12.418517%]; 8/8 improve | Its fixed gate passes |

The cohorts were fixed in advance and remain separate from discovery. See [the protocol](PROTOCOL.md), [machine-readable rules](protocol.json), and [current binding status](publication-status.json). A result is added only after a valid terminal result and its integrity review are available. No candidate source changes or sample extensions are permitted after effects are observed.

The sixteen fresh confirmation pairs all improved Cargo Ir; their pooled **12.3839397%** reduction is descriptive only, with no pooled significance or acceptance gate. Discovery is excluded. The instruction result does not override the inconclusive native result.

The workload is uv `3d82a6ad5a7eab8c68236553b7846517767c4b61` with Ohm `1.99.0-6`, `cargo -Zohm-defaults=yes test --no-run --locked --offline -j 8`, on CPUs 0–7. A controlled equal-length non-doc comment edit triggers each dirty build; original source and Cargo bytes are restored afterward. No uv tests execute. The optimization applies to command preparation in the actual check/test build phase. This package contains no other Cargo candidate.

Use [REPRODUCE.md](REPRODUCE.md) to rebuild/rerun a separately admitted fixture and recompute the saved counts. All 38 accepted discovery/check/confirmation profiles are retained byte-for-byte inside gzip files. [Source identities and the patch](source/identities.json), [binary/build identities](build/identities.json), [the mechanism](MECHANISM.md), and [focused correctness coverage](correctness.json) are included.

Important limits remain visible: the baseline binary was preserved rather than rebuilt; producer affinities differed; complete historical environment equality is unavailable; instruction cohorts record background activity under a prospective policy; every discovery profile reports the known Valgrind `brk segment overflow` fallback; and one narrowly enumerated output has two permitted whole-file hashes. The latter differs in loaded build-ID metadata, so full loaded-image byte equality is not claimed. The ordinary uv library-test executable is outside the four cached-relink executable guards.

Raw environments, host process argv, transport/authentication logs, and discarded effects are omitted. The raw profiles retain their intrinsic workload command and source/object paths. Previously discarded attempts, including v3 and M4 effects, were not opened for this package and are not reused. Source publication is recorded separately from the measured build identity; normal CI and PR publication are outside this measurement package's authority.
