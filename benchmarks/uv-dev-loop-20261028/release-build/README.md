# Release-like Cargo builds

Each file in `bin/` comes from the same source pathname, Cargo target directory, Cargo home, Rust compiler, standard library, and native C compiler. The frozen source export and archived patch inputs are identified by `provenance.txt`, `patches.sha256`, and `source-lock.sha256`. Source file hashes after each stage, exact Cargo arguments, elapsed seconds, verbose version, binary hash and dynamic linkage are under `logs/`.

The builds use the released Ohm Cargo as driver with its experimental defaults disabled for compiling the binaries. The resulting Cargo binaries enable the release's `ohm-defaults` and `all-static` features. All six carry identical frozen version metadata, including the release commit, for stable tool identity. Consult the binary SHA-256 and staged patch list to identify a particular binary.

| Binary | Changes accumulated over the released source |
| --- | --- |
| `base` | Release source export |
| `unit` | `unit-deps.patch` |
| `warnings` | Previous plus `manifest-warnings.patch` |
| `feature` | Previous plus `feature-deps-small.patch` |
| `depfile` | Previous plus `depfile-render.patch` |
| `semver` | Previous plus `lock-version-req.patch` |

From the chat workspace, the setup commands were equivalent to the following. `work/cargohome/registry` is the populated, read-only seed for this build's initially private registry copy. Cargo downloaded the locked OpenSSL source from the registry mirror on the baseline run. Later builds are offline.

```sh
lab="$PWD/work/release-like"
release=a0c7d08c898d3fdff992f2f431dec57d2486add2
mkdir -p "$lab"/{src,bin,logs,patches,cargo-home}
cp -a --reflink=auto work/cargohome/registry "$lab/cargo-home/"
git -C work/ohm-cargo archive "$release" | tar -x -C "$lab/src"
git -C work/ohm-cargo show -s --format='%H%n%h%n%cs' --abbrev=9 "$release" > "$lab/src/git-commit-info"
for name in unit-deps manifest-warnings feature-deps-small depfile-render lock-version-req; do
    cp "work/$name.patch" "$lab/patches/$name.patch"
done
awk '$1=="+++" {sub(/^b\//,"",$2); print $2}' "$lab"/patches/*.patch | sort -u > "$lab/affected-files.txt"
(cd "$lab/src" && sha256sum Cargo.lock git-commit-info > "$lab/source-lock.sha256")
bash "$lab/build-one.sh" base
bash "$lab/build-rest.sh"
bash "$lab/build-semver.sh"
```

This configuration uses the released Rust compiler with ThinLTO, one codegen unit, a release build and vendored OpenSSL, Git, curl and zlib. The official distribution’s Rust bootstrap additionally uses its merged rustc/Cargo PGO training profile. The release workflow only retained the toolchain archive, provenance and checksums. These secondary binaries are locally compiled without PGO. The Linux BOLT stage operates on the Rust compiler driver. [Released bootstrap configuration](https://github.com/astral-sh/ohm/blob/fdf90406638cacb725178ee17e67957f7bd662ca/release/bootstrap.toml), [Linux distribution build](https://github.com/astral-sh/ohm/actions/runs/40609224340/job/122556727152), [pinned opt-dist pipeline](https://github.com/astral-sh/ohm-rust/blob/bfa236f639034f61ec884c15bd1f4e0b75e508ac/src/tools/opt-dist/src/main.rs).

`published-identities.tsv` maps each cumulative source stage to its published pull-request commit and tree. Run `python3 audit-prs.py` to verify the staged fingerprints of all seven touched files against all six Git trees. Run `python3 audit.py` to verify every adjacent patch, binary digest, reported version, shared-library list and build duration. These checks operate on the files produced by the recorded builds.
