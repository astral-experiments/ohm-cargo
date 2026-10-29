# An edit confined to the Ruff ty_server test executable

Ruff changed an inlay-hint end-to-end test to use a local Python class, `Thing`, so its expected result no longer depended on the line number of `int` in typeshed. The commit changed one Rust source file in the test executable. At the benchmark revision, its complete patch applies in reverse and applying it forward restores the exact original source bytes. [Original Ruff change](https://github.com/astral-sh/ruff/commit/1b9310471b7d1178633e58ee63808522609db887)

The edited state reverses that whole commit against Ruff `93526150`. A separate failure control inserts a type error in the same test. The test name is `inlay_hints::default_inlay_hints`. An independent clean build must establish how the historical typeshed line assertion behaves on this newer Ruff revision. This packet records source preparation only.

From this directory, run `sha256sum -c SHA256SUMS` and `python3 -IB verify.py /path/to/ruff`. The verifier reads the four pinned Git objects and applies the historical patch in a temporary directory.
