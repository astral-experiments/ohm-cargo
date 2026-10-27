# Native incremental reexport regression

A three-crate workspace contains an rlib producer, an ordinary rlib which does a public glob reexport and forwards generic calls, and a separately editable binary. The leaf has one private optional sibling file, a public struct and generic functions in a different file, and an unreachable private Iterator impl. The five ordinary Cargo calls per case prime the binary, edit only the producer, edit only the binary source, restore the producer, then restore the binary. Fresh references build the real edited and restored caller in independent empty target and shared directories at the same canonical source paths. The experiment uses default `cargo +ohm build -p app` with the repository's dev optimization and line tables. Every executed test binary is the fixture's workload and prints its observed results. No timing was collected.

The candidate driver `55e123a9e87f16a449d260ab65449eab743cd30ba356a7f10ffdd1fa6f8a2484` is the exact original #233 head. The parent driver `051b9d3f5861f984faa0f8c1d2ab9b5c28e483a05c728051de837291c83fd518` is the measured #232 control. All six arms use PGO Cargo `71da9dfcb3ba440297f84705ff7e3a676634ced7d7b6ca9b525a439b7f748f58`.

| Private producer edit | #232 parent with subsequent caller edit | #233 candidate with subsequent caller edit | Entirely fresh target |
| --- | --- | --- | --- |
| Activate one cfg-disabled private source file, change private associated Item u8 to i8 | Full intermediate was rebuilt; caller compiled | Intermediate was reused; caller panicked in module_children | Both succeeded |
| Change the private associated Item only | Full intermediate was rebuilt; caller compiled | Intermediate was reused; caller compiled | Both succeeded |
| Activate the private source file only | Intermediate was reused; caller panicked in module_children | Intermediate was reused; caller panicked in module_children | Both succeeded |

The failure occurs on the second real edit. After the first edit the candidate relinks the executable successfully. Changing the caller source then asks a fresh rustc process to compile that crate and trips the incremental `module_children(bundle)` consistency check. The unchanged-source behavior already exists on both compilers in the file-only control. Root's independent released-R14 control is recorded separately. The withheld draft fix must pass the combined edit, the single-factor controls and independent clean references.

`rows.json` records all 30 warm invocations and 12 cold references, actual compiler and link-only selections, exact source/tool/product hashes and runtime/diagnostic outcomes. `args.json.gz` contains NUL-separated original child argv by SHA. The three original failure logs and machine-specific runner are included; run `python3 rlib-real.py files_types 1 <new-dir> <cargo> <driver>` with the published inputs.
