# Native location hashing in rustc

The one-file rustc change reads the tracked span once and uses its start and end positions for source lookup, containment and endpoint hashing. The compressed patch contains the full parent-to-child diff with Git blob IDs. Both optimized stage1 builds used the same four bootstrap inputs, 119 literal native compiler commands and 53 standard-library artifacts. The driver is the only different member of the compiler SDK.

Both compilers passed the five existing run-make suites listed in `five-suites.json`. In the same-length module-location fixture, moving the span from column 1 to 257 changed its public hash from `8540b008200c27d18555aa6f07e2ebc2` to `177cab50a2fdd7467f2bf1a72266a6bf` in each compiler. Two native readers per compiler reported the corresponding columns. The first fixture parser expected one trailing newline. The actual listing has two. The five suites were rerun with that parser correction, on fresh fixtures in both arms, and their source inputs stayed identical. The original run and amendment are retained in the hashed custody record.

Run `python3 -IB verify.py` here to check the construction and behavior receipts, and use the sibling instruction packet for the Ruff workload and all 48 measured compiler processes. [Ruff instruction packet](../native-location-ruff-instructions)
