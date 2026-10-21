# Original PR175: output remapping plus loader handling

The frozen two-change composition passes both predeclared Cargo-process
instruction gates on unchanged uv. It does not pass the full native wall-time
gate on either workload.

| Workload | Metric | Reduction | 99% interval | Gate |
|---|---|---:|---:|---|
| check | Cargo instructions | 3.629665% | 3.536659–3.671840% | Pass |
| test --no-run | Cargo instructions | 3.182471% | 3.097137–3.222845% | Pass |
| check | Native wall time | 0.406989% | −0.337321–1.130792% | Fail; interval crosses zero |
| test --no-run | Native wall time | 0.808496% | 0.149413–1.543692% | Fail; below the 1% minimum |

The native test-build result has a positive statistical signal: its 99%
interval excludes zero and its paired sign-test p-value is 0.005223. Its point
estimate is below the frozen practical threshold, so it is not an accepted
native speedup. The native check result remains inconclusive. Both instruction
comparisons won all 12 pairs, with two-sided sign-test p = 0.00048828125 and
positive results in both AB and BA order groups.

This comparison uses the original PR175 source and predates the external
restack. It measures the composition directly and does not add separate
candidates' percentages. It makes no claim about the subsequently restacked
heads, the later four-change stack, cold builds, or source-edit builds.

Baseline source is original PR175 efc8b51502f8a8d1fe76997dc984481edde2740e,
tree 3d67bfb965bc0b6452ab78205045c5154db0acf7. Candidate tree is
4117e012ab1e082867dcb5a4b2a227e7f5200ff6. Frozen stripped binary SHA256 values:

- Baseline: 63495905e7b0b11ad99fa4c2c2674e43657b9902a2e3142ef735fd83efa44cf8.
- Candidate: a60f7c6ccb37c582263a02b462673de9b7d5e7a68127258d150be49f1b1721be.

The fixed instruction batches used 12 randomized balanced pairs and two
warmup pairs per workflow. Native confirmation used 30 balanced group pairs,
eight sequential executions per variant group, and two warmup pairs. The
group pair is the native statistical unit, not each of its 480 measured
subruns. Bootstrap intervals use 20,000 paired resamples, confidence 99%, seed
1701. Every attempt is retained; there was no interim effect inspection,
sample extension, pooling, or outlier removal.

See [REPRODUCE.md](REPRODUCE.md), [VALIDATION.md](VALIDATION.md),
[results/summary.json](results/summary.json), and the frozen protocols.
RAW-MANIFEST.json binds every archived file. Full Callgrind attribution files
remain in the task workspace; their hashes, sizes, event order and exact
counter lines are included. Native raw data, all preflight traces, build logs,
source patches and immutable input identities are retained.
