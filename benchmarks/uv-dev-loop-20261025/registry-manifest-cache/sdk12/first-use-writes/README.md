This is a private, portable addendum for four excluded first-use registry-cache syscall witnesses. It contains every recorded PID event and the final committed cache payloads. It is not a timing or instruction comparison.

Run `python3 -I -B reproduce.py` from this directory with Python 3.11 or newer. The replay uses only the standard library and temporary local files. It verifies the full manifest, all 68 PID traces, compiler argument/environment and diagnostic joins, the exact final payloads, and 28 decoder checks. It invokes no Cargo, compiler, tracer, network or guest command.

| Call | Successful logical bytes | Commit renames | Replacements of an earlier slot | Final slots | Final bytes |
| --- | ---: | ---: | ---: | ---: | ---: |
| Host 1 baseline | 0 | 0 | 0 | 0 | 0 |
| Host 1 candidate | 847,429 | 470 | 25 | 445 | 803,161 |
| Host 2 candidate | 847,429 | 470 | 25 | 445 | 803,161 |
| Host 2 baseline | 0 | 0 | 0 | 0 | 0 |

All four original native Cargo commands and restoration commands returned zero. All four collectors subsequently stopped in the original parser: the `>` in a numeric UNIX socket `source->peer` annotation was mistaken for the end of the fd annotation. The four-line offline grammar repair is included beside the byte-exact original, its reversible diff, and regression/refusal checks. It drops no syscall and changes no accounting function. Each original command ran once; no replacement acquisition occurred.

The complete traces reconcile every successful cache-temp write and rename in local PID order. Both candidate calls have one cache-mutating PID, no failed or partial writes, and no failed commits. The last committed payload for every slot equals the separately captured final bytes. The 803,161-byte footprint was a lower bound: replacements account for the additional 44,268 logical bytes.

The original post-parse dirty-output snapshot was never reached. Read-only snapshots of all four parked outputs match their already fixed dirty references, but restoration recompiled `uv`; these snapshots do not prove that no intervening writer changed the original dirty outputs. That gap stays explicit in every disposition and in the replay result. Source/Cargo restoration and parked banks were independently retained before the hosts were released.

Path substitutions preserve UTF-8 byte lengths, syscall return values and all cache payload bytes. No syscall is removed. The complete private archive digests remain in the per-call dispositions. Private process/connection records and host identity details are omitted. Incidental timestamps and diagnostic text are provenance, not wall-time samples.

These are successful logical bytes accepted by write-family syscalls. They do not measure physical device writes, writeback, filesystem metadata, allocation, amplification, or durability. The tracer source archive, compatibility patch, build recipe and binary digest are pinned separately; the capture command and exact syscall selection are retained. The two instruction studies and the native safeguard have separate protocols and decisions.
