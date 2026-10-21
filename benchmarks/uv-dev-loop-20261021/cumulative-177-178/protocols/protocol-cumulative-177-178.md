# Combined PR177 and PR178 validation

Frozen 2026-10-21 11:18 UTC before the combined binary is available and before any combined timing.

Purpose: verify that the two accepted changes compose and quantify warm-loop instruction effects of their combination. Individual effects are not assumed additive. This produces validation evidence, not a separate source PR.

Baseline is PR175 efc8b51502f8a8d1fe76997dc984481edde2740e. Candidate is PR175 plus the exact accepted build-output-remap and loader-v2 patches; expected tree 4117e012ab1e082867dcb5a4b2a227e7f5200ff6. Source patch SHA256 values are a967d4353a4dc3dc252a45231dada1a3f01b27d7f206c0c16f69c61e9796d265 and be2146042f257eb1e36f3d5de804a2ff991f87676b5fe38fe4a5d6a30c4ea1e9. Binary provenance and final configs must be sealed before measurement. Use the same source/target build paths, compiler, flags, embedded Cargo identity, strip audit, native environment and pinned uv as the independent validations.

Fixed warm confirmations:
- Cargo-only Callgrind instructions: 12 check pairs, seed 2026102141; 12 test --no-run pairs, seed 2026102142; two warmup pairs each.
- Native wall/CPU time: 30 check groups, seed 2026102143; 30 test --no-run groups, seed 2026102144; eight calls per group, two warmup pairs each.
- Check is primary; a separate test-build claim requires its own full gate. Acceptance requires at least 1% reduction, positive 99% paired bootstrap interval (20,000 resamples, seed 1701), exact two-sided sign p <= 0.01, and positive effects in both orders. No established native regression is permitted. Native and instruction claims require their own gates.

Preflight each variant/workflow with an untimed native execution trace and require no compiler, build-script, linker or test execution in these fresh commands. Preserve all fixed samples and failures; no extensions, pooling, interim effect inspection or effect-based stopping. Input/binary/source/runtime hashes and fixture freshness must match before and after. Instrumented elapsed time is not native timing. Existing serial benchmark leases take precedence.

A separate composition smoke test may exercise the native-test-to-check transition with up to four fixed pairs (seed 2026102145), independent fresh native seeds and the exact restore/audit machinery used for PR178. This is solely a correctness/mechanism check: it must verify native artifacts, test --no-run, no test execution, consistent reuse and successful check outputs. It cannot support a new combined wall-time claim and must not be pooled with the 12-pair PR178 confirmation. Stop and investigate any integrity/correctness failure.
