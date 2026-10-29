# C5 native timelines

The 16 unscored before/after traces cover both arms of the two stationary batches, the plain holdout and the edit holdout. Each trace records one observing `ron` compilation, 50 link-only rustc invocations, 50 real stock Wild links, and the Cargo process. Each target is matched by the actual Wild → collect2 → GCC → rustc → Cargo process lineage.

`timelines.json.gz` reports exec and exit times in nanoseconds relative to the first Wild exec in the same trace. Negative times are expected for Cargo, rustc or GCC work that started before the first Wild. Wild exits and Cargo and rustc exits were recorded by the same wait4 tracer. Every target includes its completed native file size and SHA-256. The prior size and digest came either from the named, authenticated donor inventory before that section or from the last traced native inventory for the same physical lane. The tracer did not stat the incumbent when Wild started. All 800 prior and completed sizes agree.

For each trace the offline verifier recomputes maximum concurrent stock links, maximum sum of output-file sizes for concurrent links and the elapsed intervals with at least two or four active links. The sum of file sizes is a workload weight. The four independent pairs of before/after diagnostic traces on each arm are separate from the registered wall-clock samples.

Run `python3 -IB verify.py` to recheck the portable timelines. With access to the preserved private traces, `project.py STUDY_ROOT` emits the complete gzip projection again from the recorded process starts and exits.
