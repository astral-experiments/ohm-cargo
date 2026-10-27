# Native links that look removable in Ruff

Four Ruff CLI integration test binaries omit `ruff_linter` from their actual native inputs. Their build scripts also introduce GCC and linker search paths. An archive found through one of those paths changed a real program from 41 to 83 while the Rust externs remained unused. Adding an earlier archive changed the program while every file in the original Wild dependency list retained the same digest. Adding GCC’s previously absent `specs` file changed which paths reached Wild, then removing it restored 41. The evidence includes the complete runnable fixtures, release tool identities, ELF hashes and typed lookup records.

On the historical ty comment, all 15 ordinary build ELF hashes matched the original sources. The ordinary test build launched 19 Wild processes. Of its 110 workspace ELF hashes, 109 matched the original baseline and all 110 matched after edit and restoration. These measurements used the default GCC route. The separate clang-wrapper results have their own receipts in the archive.

The proposed Cargo rule could retain a stale executable in these controls. Its implementation was excluded from the performance comparisons. The registered compiler and Cargo changes use their existing linker behavior.
