# Cost of checking the released linker's selected input bytes

Three actual Ruff executable links cover the three native search-directory groups observed among 50 repeated Wild invocations. One pinned release-profile compiler replay per target reconstructed the original link operands. While its temporary files still existed, stock Wild `0d633580…` wrote a real Make dependency file. It then linked without the reporting option at fixed width eight. All three resulting ELF files matched genuine full-workspace output hashes.

| Target | Project search directories | Resolved files | Bytes | Full Wild | BLAKE3 |
| --- | --- | ---: | ---: | ---: | ---: |
| `simple_tokenizer` | psm | 148 | 95,005,487 | 35.46 ms | 21.45 ms |
| `document` | psm, zstd-sys | 289 | 442,853,145 | 107.25 ms | 52.84 ms |
| `ruff` binary test | psm, zstd-sys, jemalloc | 311 | 500,166,915 | 81.56 ms | 61.99 ms |

The table contains component medians from six interleaved pairs on one x86-64 Linux host. Both programs used CPUs 4–11 under an exclusive benchmark lock. Each native link verified the full output afterward. The reader used the official BLAKE3 1.8.7 C implementation with runtime SIMD dispatch, seven helper threads and one calling thread. It opened, mapped and hashed every file in the depfile and returned a distinct digest for each. Every measurement returned exactly the same digests. The runner included spawning and receiving/parsing the hash list in the BLAKE3 elapsed time. Full ELF output verification ran outside the measured Wild interval. Known-answer vectors and one independently built file hasher checked the reader. All times and source identities are in `costs.json.gz`; the unusually slow 225 ms `ruff` Wild sample is retained.

Every native dependency report included the same 19 external files, including `libgcc_s.so`, `libm.so` and `libc.so` as GNU linker scripts. The GCC script uses a relative `libgcc_s.so.1` and a fresh `-lgcc` search. The libc and libm scripts use absolute names and `AS_NEEDED`. A depfile describes the paths the preceding link selected. It cannot establish that a different earlier library-search candidate is still absent. Temporary plugin inputs are outside the linker's depfile format.

Separate enumeration of all 50 actual argument lists in one unchanged Ruff run found 11,779 still-materialized file operands, accounting for 12,656,036,748 bytes with repetitions. At examination time they referenced 3,397 distinct filesystem inodes totaling 1,410,373,480 bytes. One now-removed `symbols.o` file per link and all implicit library searches are excluded. This census describes shared bytes, without establishing immutable or synchronized access to them.

These engineering measurements exclude Cargo, rustc, a coherent previous-output witness, changes in lookup resolution, and preserving linker side effects. They support no whole-workspace performance claim. Run `python3 -IB verify.py` to replay the offline checks.
