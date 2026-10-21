# Instruction profiling restored before candidate batches

On 2026-10-21, supplying the existing certificate defaults explicitly avoided
OpenSSL's startup `setenv` call and allowed Callgrind to run the complete fresh
uv check. Both native and instrumented variants use:

```
SSL_CERT_FILE=/etc/ssl/certs/ca-certificates.crt
SSL_CERT_DIR=/usr/lib/ssl/certs
```

These select the same trust store the pinned openssl-probe 0.1.6 had already
selected automatically. No libc code, runtime probe, monitoring process or host
security configuration was changed. The profiler-only constructor removes
Valgrind's own loader variables before Cargo starts, so compiler children would
receive the ordinary native loader environment. Fresh-workload diagnostics
compile no crates, and counts cover only Cargo, not child processes or the
kernel. Instrumented elapsed time is never used as a native timing result.

The successful diagnostic pair is retained separately and is not confirmation
evidence. The original instruction protocol applies: eight exploratory pairs,
twelve independent confirmation pairs, two recorded warmup pairs per batch,
balanced randomized order, >=1% point reduction, 99% interval excluding zero,
exact two-sided sign p<=0.01, and a positive effect in both order groups.

Callgrind 3.22 reports its known brk-segment limit on both variants; the commands
complete successfully using the allocator's fallback. Counts are emulated user
instruction references under this environment. Native confirmation uses the
grouped timing protocol and does not inherit profiler loader settings. It may
run on a separate quiet host, provided each native pair uses identical frozen
compiler/binary assets, paths, environment and cache setup on that host. Never
compare absolute times across hosts. Report both hosts and retain all inputs.
