# A retained linker object can overwrite rustc’s incremental work product

A Rust program and its path dependency initially print `17 7`. An independent build from genuine alternate source supplies a same-sized object that returns 29 instead of 17. The experiment then restores a fresh target and the original source before each case. It changes only the saved linker object, preserves its length and modification time, and edits the dependency to return 11. The ordinary command is `cargo +ohm build --locked --offline`.

| Operation on the retained object | After the dependency edit | On the next unchanged build |
| --- | --- | --- |
| Leave the object alone | `17 11` | `17 11` |
| Atomically replace the directory entry with the alternate object | `17 11` | `17 11` |
| Write the same alternate bytes into the original inode | `29 11` | `29 11` |
| Start with empty target and shared-build directories | `17 11` | |

Cargo returned success in every case. All three dependency edits ran a full rustc for the dependency and root plus a real stock Wild link. Each immediately following unchanged build ran zero compilers and zero linkers. A later root edit to 41 recovered the correct executable and matched an independent empty build byte for byte.

Before mutation, the saved object and the incremental work product named the same device and inode. The in-place write changed the hash through both names. An atomic replacement kept the incremental hash intact. Cargo’s per-object digest detected the changed object and ran a full compiler, but rustc could still use the poisoned incremental work product.

The file reproduces on the downloaded Linux x86-64 releases 1.99.0-17, -18 and -19. Each release replay saved the observed ELFs by digest and executed them again independently. We also reproduced the result on a second isolated signed -19 run and on rustc `ad005f99d0b51fd62b5c237bc13b31b371a1686e` with both the proposed release Cargo `7277e6cdaba44c43294a07c0661fc8e69fd8e3e7` and Cargo `84af87848a5a952ba61ae6a2cc5b22da24130200`. The six observations cover 90 real Cargo commands. These experiments exposed the bug by deliberately modifying a build artifact.

Verify the command inventory, real outputs, source hashes, inode relationships and negative controls.

```sh
sha256sum --quiet -c SHA256SUMS
python3 -IB verify.py --self-test
```

To reproduce, use Linux x86-64, the SDK selected as `+ohm`, Python 3.11 or later, strace, binutils and a new directory. The fixture has no registry dependencies. It creates independent target and shared-build directories, preserves every native trace, and copies each observed executable into `work/elfs` by SHA-256. A fixed compiler should pass the same command with `--expect correct`.

```sh
python3 -IB probe.py "$PWD/work" --expect stale
```

The successful and stale executable hashes live in `work/result.json`. To execute the two preserved binaries directly on the same machine, run the following.

```sh
python3 - <<'PY'
import json, subprocess
from pathlib import Path
work = Path("work").resolve()
result = json.loads((work / "result.json").read_bytes())
for row in (result["outputs"]["in-place"]["edited"], result["clean17"]):
    subprocess.run([work / "elfs" / row["elf"]], check=True)
PY
```
