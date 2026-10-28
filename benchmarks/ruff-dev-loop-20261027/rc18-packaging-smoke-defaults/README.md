# Cargo defaults in the release smoke test

The smoke test on packaging main expected every toolchain to enable the persistent proc-macro expansion cache. It accepted the published -17 Cargo and rejected the corrected -18 Cargo. The version-aware check accepts the correct pairs and rejects an old Cargo executable labeled as -18.

| Smoke test | Manifest revision | Cargo executable | Result |
| --- | --- | --- | --- |
| Current main | 17 | Published -17 | Passed |
| Current main | 18 | Corrected candidate | Rejected during the defaults build |
| Candidate | 17 | Published -17 | Passed |
| Candidate | 18 | Corrected candidate | Passed |
| Candidate | 18 | Published -17 | Rejected during the defaults build |

Every passing row ran the real package smoke crate with defaults and opt-out in separate targets. The five commands used the installed Linux -17 compiler to isolate Cargo. The -18 manifest in this fixture supplied the candidate version and Cargo pin. Full release artifacts are a separate gate.

Run `python3 -IB verify.py --packaging-git /path/to/ohm` to verify all results and match the two shell excerpts to their source commits. The verifier also works without a local Git checkout. The archive contains exact shell, Cargo stdout and stderr, and the wrapper’s actual per-build flag observations. [Packaging change](https://github.com/astral-sh/ohm/pull/197)

