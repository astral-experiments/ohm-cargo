# What changed when Cargo started the largest ready test links first

This post-study reconstruction covers all twelve off-clock native qualifications from the two H8 batches, with 50 real stock Wild invocations per command. The ordinary wall study separately measured an 11.87% slowdown across 96 pairs. The qualifications preserve the exact native arguments and ELF checks from that study. Their service durations and this report’s hardware observations are descriptive.

| Median across six native checks per arm | Default | Largest first |
| --- | ---: | ---: |
| Time from final Wild launch to final Wild success | 762 ms | 23 ms |
| Overlap between pairs drawn from the ten largest links | 9.34 pair-seconds | 23.02 pair-seconds |
| Maximum total size of concurrently linked output files | 1.363 GB | 1.584 GB |
| Time from final rustc exit to Cargo exit | 415 ms | 1,343 ms |
| Time from final rustc exit to the last typed stdout write | 253 ms | 1,221 ms |

The largest ten had 4–6 simultaneous Wild parent processes under default and 7–8 under treatment. Pairwise overlap rose in every matched check. The last native target was a large library or integration harness in every default check and a small test tool in every treated check. Wild’s normal Unix parent waits until its child reports that the output is written. Its exit bounds the caller-visible link, while a child can finish cleanup afterward.

The native launch tail shortened in all six comparisons. In five, Cargo spent longer after its last rustc exit. The kernel mtime on the original output stream containing the final build-finished record confirms that most of this interval preceded the final write. The sealed native checks did not trace the cause of that wait. The host counters in the scored study span both arms of each pair and cannot attribute an individual arm’s delay.

## Supplementary kernel observation

One diagnostic sequence was allowed. A fresh private copy ran A, B, then A using unchanged source, the same privileged namespace setup as the original study, and unprivileged Cargo. All three returned zero. The first A rebuilt ty_vendored and downstream crates, emitted 619 records with 548 fresh, and launched 58 Wilds. It is excluded. Its first receiver also missed Wild’s token record. The final receiver was independently checked against a real GCC and stock Wild link with a two-worker jobserver. There was no fourth Ruff command.

The settled B and final A had 619 records with 563 fresh and one full rustc compiling ron. Across both, all 51 Rust argument vectors and all 150 GCC, collect2 and Wild argument vectors matched each other and the signed earlier qualification after verifying three temporary operand roles by live contents. Both passed the same 200-entry ty_server e2e listing and both real notebook regression tests. All 50 ELF files matched between the settled commands under the earlier strict variant rule. Forty-nine matched byte for byte, including the e2e file. Only direxist_guard varied in the GNU build ID and the .rodata section-header entry size (0 at width one, 8 at width two).

The strict comparison against the earlier signed products still rejects nine of the scratch binaries. The private checkout copy changed the directory iteration order in the ty_vendored build script. Of 819 members in its 1,565,618-byte ZIP, 815 moved. Every member’s compressed and expanded bytes, sizes, timestamp, flags and external attributes were identical by filename. Replacing that single embedded ZIP reconstructs the entire changed .rodata payload in all nine executables. The only other changed section payload was the GNU build ID. The two settled observations therefore supplement the original native checks without replacing any gate.

| Scoped kernel observation | Default, final A | Largest first, B |
| --- | ---: | ---: |
| Wild processes with one / two acquired workers | 50 / 0 | 49 / 1 |
| Peak assigned worker budget live at once | 8 | 8 |
| Peak sampled runnable Wild tasks | 8 | 8 |
| Median sampled runnable Wild tasks during active linking | 6 | 7 |
| Total CPU time across Wild processes and threads | 21.66 s | 28.05 s |
| CPU time in the ten largest links, all at width one | 9.50 s | 12.79 s |
| Kernel runnable-queue wait summed across Wild tasks | 5 ms | 25 ms |
| Peak sampled Wild PSS | 1,731 MiB | 2,235 MiB |
| Time from last rustc exit to Cargo exit | 61 ms | 58 ms |

Stock Wild’s own token write reports additional tokens for each scope. Its effective worker count adds the implicit parent token. The observer recorded successful execs, complete argument bytes, process and thread exit accounting, and the genuine writes on the kernel tracepoints with zero lost events. Runnable includes tasks executing and tasks waiting to execute. The process sampler targeted 40 ms intervals, with median steps of 40 ms and 95th percentiles of 90 and 122 ms. PSS was sampled separately every 350 ms. The observer consumed 2.19 and 2.77 CPU-seconds, respectively. The kernel accounted approximately 3.95 GB of Wild output writes in each arm. Every one of the ten largest links took longer in B and nine consumed more CPU. Memory bandwidth, cache stalls and per-arm frequency were not measured. The long Cargo tail from the earlier study did not recur here.

## A bounded candidate to test against default

The best supported experiment is to keep default dispatch except when its next native test would be a fourth large active job and a short eligible job of the same dependency priority is already waiting. In that one circumstance dispatch the short job, keep the slot occupied, then reconsider normal order at the next dispatch. As exploratory fixed thresholds, at least 128 MiB for large and at most 32 MiB for short classified 14 and 23 of the 50 native targets. In three released Cargo queue logs, 10, 7 and 10 actual default decisions met those conditions. These counts describe opportunities on the observed path, not the number of swaps in a future run.

The interval evidence supports testing a limit on large-job overlap. Among the ten largest equal-input targets across the six matched checks, 28 began with three or more other large Wilds active under B and at most two under A. In 21 of those comparisons the same target completed more slowly in B, with median duration 9.6% longer. Launch order, worker availability, and shared system state were not independently randomized for these comparisons. There is no demonstrated whole-command win over default. An off-clock qualification would first need to reduce peak overlap without extending the end of the job queue or changing native work, outputs, or diagnostics.

Run `sha256sum -c SHA256SUMS` and `python3 -IB verify.py` in this directory. The kernel files retain relative event times, thread ownership, scheduler counters and the observed widths. The original absolute native arguments remain private and are bound by their digests.
