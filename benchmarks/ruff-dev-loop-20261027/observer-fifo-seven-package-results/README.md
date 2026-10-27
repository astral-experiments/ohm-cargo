# Revalidating genuine compiler inputs on seven packages

The exact proposed Cargo and its matched #253 control were run with the same #233 rustc. Each pair measured an ordinary native build on unchanged source and then added or removed one byte before a token observed by a procedural macro. Two binaries printed a different source span after the edit. The third served as an unchanged control. Each binary's stdout and complete ELF hash matched an independent empty-target build for that version of the source on all 114 commands. [Registered subjects, schedule and analysis](https://github.com/astral-sh/ohm-cargo/tree/6a2cd57b78aac92255c60a3566c107119c07e429/benchmarks/ruff-dev-loop-20261027/observer-fifo-seven-package)

| Input | Parent median | Candidate median | Paired time reduction (95% CI) | Faster pairs | Holm p |
| --- | ---: | ---: | ---: | ---: | ---: |
| Unchanged | 190.2 ms | 98.3 ms | 47.8% (46.7 to 49.0%) | 12/12 | 0.0043 |
| Genuine one-byte edit | 345.7 ms | 484.8 ms | −38.0% (−40.7 to −35.2%) | 0/12 | 0.0043 |

On every unchanged process audit the control launched two full rustcs and one link-only rustc. The candidate launched none. After every genuine edit both arms launched four full rustcs and one link-only rustc. The candidate recorded the inputs of the two readers in those builds.

The two cold references, sixteen training commands and forty-eight process audits ran outside the timed comparison. Run `python3 -B verify.py` to rederive both two-sided balanced randomization tests and the paired intervals from all 48 ordinary commands, and check all process counts and native outputs. [Runnable harness and exact fixture](https://github.com/astral-sh/ohm-cargo/tree/825a3cdd1d19be6a9e86bef9c2942cee57bfa5ac/benchmarks/ruff-dev-loop-20261027/observed-span-holdout)
