# Pending metadata dependencies on Genoa

Both directions use all 30 changed files from Ruff 716260bf10d7 to 2d6ce561250a. Each check selected 510 artifacts across 47 workspace members, using the locked dependency set and the released -18 Rust compiler and Wild.

| Destination | Cargo | Full rustcs on edit | First unchanged | Second unchanged |
| --- | --- | ---: | ---: | ---: |
| Parent | Historical PGO control | 51 | 12 | 1 |
| Child | Historical PGO control | 51 | 24 | 1 |
| Parent | Debug candidate | 56 | 1 | 1 |
| Child | Debug candidate | 56 | 1 | 1 |

Every edit linked the real `ruff_macros` procedural macro once. The repeats ran no linker. Both selected metadata files retained their complete SHA-256 across all 14 commands. On the control, the newer AST dependency timestamp appeared in the subsequent fingerprint diagnostic for index in both directions.

The initial candidate check following restoration of the control's 30 source files ran `ty_python_semantic` and `ty_vendored`. The two previously settled checks of each executable ran only `ty_python_semantic`. This unscored debug comparison used a common captured output state while the 30 source files remained in the private linked worktree. The independent matched release comparison has a separate source-and-output snapshot.

The candidate also returned the identical complete E0624 diagnostic in warmed and empty targets after restricting visibility of the real AST method. Restoring the declaration repaired it. Changing a separate private method body compiled 34 workspace units physically and settled to one in both directions.

The original no-link assumption for the edit failed on the real procedural macro. All raw commands were retained. The corrected verifier joined each actual linker output with the corresponding Cargo artifact. Btrfs rejected a cross-subvolume move while preparing the empty-error control, before the compiler was called. That control subsequently used an independently empty target and shared directory. The evidence binds raw inputs and outputs by SHA-256. These are structural observations from two different Cargo build profiles.
