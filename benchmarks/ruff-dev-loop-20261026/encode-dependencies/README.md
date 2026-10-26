# Omit unused fields while encoding lockfile edges

Compare Ohm Cargo `461a3d1007ecc997a6d86c7d75e8b518575c8d90` and `fc82ecb6f31cea7da5dba628e697fe80ed05acd9` on unmodified Ruff `93526150df078af7dd8fc4226cdcc469539d2001`. The first release-profile Cargo binaries were built with `--features ohm-defaults`, release incremental compilation and no PGO, and used the published x86-64 Linux Ohm 1.99.0-14 rustc. The PGO holdout used the release’s compiler and Cargo training data with release incremental compilation disabled.

Each measured command processed the same list of fresh artifacts as its parent, with 520 for check, 501 for build, and 619 for test compilation. The first workspace used a per-thread DynamoRIO instruction counter on Cargo and counterbalanced five-arm blocks. The independent two-arm check used Valgrind Callgrind with child tracing on a second checkout. With every artifact fresh, each measured Callgrind invocation produced a single Cargo process profile. The CSV retains relative arm order, paired counts and artifact totals.

Use the [portable fresh-command harness](../registry-manifests/) with `--design paired --pairs 12 --artifact-messages --mode check` and no package selector. The same command also supports `--mode build` and `--mode test`. The Cargo binaries use a stable path to prevent the path spelling from contaminating the comparison. The two-sided randomization test enumerates all label assignments with the observed arm-order balance.

A separate 40-pair native wall-time check was inconclusive. Instruction counts are the supported metric.

The PGO holdout saved 0.394% in 12/12 full checks, with an exact two-sided randomization p-value of 0.00216. The independent standard release-profile Callgrind check saved 0.362% in 12/12 pairs (p = 0.00216). The CSV includes every comparison from each complete cohort.
