# Independent object storage in the repaired compiler

Rustc `05efba7a06f5bb71d1efb4b86805800f8b810779` produced the clean executable after an in-place write of authentic alternate machine code. The same program passed with the release-pinned Cargo and with the native-link companion. In each of six independently seeded object treatments the saved object had one link. We ran every preserved executable again by its SHA-256.

The committed rustc run-make test overwrote both new and restored object files with invalid bytes. The signed -19 driver stopped on the second rustc invocation with a native link error. The fixed driver finished three complete compiles and the resulting program printed the expected value after each one.

| Result after the actual dependency edit | Fixed release Cargo | Fixed companion Cargo |
| --- | ---: | ---: |
| Untouched retained object | `17 11` | `17 11` |
| Replacement using rename | `17 11` | `17 11` |
| Replacement by in-place write | `17 11` | `17 11` |
| Later root source edit | `41 11` | `41 11` |

Both Cargo versions ran a full rustc for the dependency and the root plus one stock Wild link on each dependency edit. Each next unchanged command executed zero compilers and zero linkers. All the edited and restored executables matched their own independent empty builds.

```sh
sha256sum --quiet -c SHA256SUMS
python3 -IB verify.py --self-test
python3 -IB ../probe.py "$PWD/fixed-work" --expect correct
```

The parent directory contains the same fixture, the published-toolchain results and its requirements. These specimens begin with empty target directories and do not measure object-copy cost.
