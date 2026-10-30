# Formatter branch-switch screen

Two counterbalanced pairs qualified a 12-pair confirmation in both directions on [astral-sh/ruff#28335](https://github.com/astral-sh/ruff/pull/28335). These timings come from six freshly empty installations on Linux x86-64, four of which supplied ordinary times. The other two supplied separate native traces and independently empty references. All 34 Cargo commands reached their expected terminal result.

| Returning to | Parent and candidate elapsed, pair 1 | Parent and candidate elapsed, pair 2 | Paired whole CPU ratios | Unique CGU output paths opened for creation |
| --- | --- | --- | --- | --- |
| A, original 64-byte Expr | 22.196 and 5.355 s | 23.201 and 5.496 s | 10.80× and 11.13× | 310 and 1 |
| B, edited 56-byte Expr | 22.563 and 5.331 s | 22.834 and 5.517 s | 11.04× and 10.71× | 310 and 1 |

Every native return ran four full compilers for ruff_python_ast, ruff_python_parser, ruff_db and ruff_python_formatter and one actual stock Wild. All 216 typed artifacts had the same names and features across runs. Each same-source executable was byte-identical to the independently empty one. Each of four complete empty suites passed 51 tests and ignored two. The actual dependency graph accepted exactly 32 correct Expr sizes and rejected 32 opposite sizes with E0308. Both compilers rejected the deliberately malformed formatter at the same span and recovered. The 96 individual representative test runs passed.

The compiler fork is [astral-experiments/ohm-rust](https://github.com/astral-experiments/ohm-rust). The source pair was 7e71d3150938ff8ed82aca03416439d7e5b87ef3 and 6b7f424ece4bc978ead5546b73e1b31d5ccb1e70. The matched optimized stage1 SDKs differed in one enrolled file, the rustc_driver. Cargo 2d44bd4a and the stock Wild binary matched by SHA. This screen establishes the behavior of those source-built SDKs on these two transitions. Its two pairs do not estimate a population-level latency effect. The separately registered confirmation uses 24 new installations.

Every ordinary visit used the same Cargo entry point.

```sh
cargo +ohm test -p ruff_python_formatter --lib --no-run --locked --offline -j4 --message-format=json
```

Both historical commits, the exact source digests, offline materials, criteria and sequence are listed in registration.md. The effects exclude Git, physical verification and tests. Source switching and external validation used the same physical paths and stock tools separately in both arms.

The summary and three corruption checks require Python 3.11 or newer.

```sh
python3 -IB verify.py
```

The independent full-scale readers accept a supplied original raw acquisition tree and zstd. This projection publishes the exact commands' receipt and output hashes, normalized typed records, executed native roles, elapsed nanoseconds and CPU values. The raw tree additionally contains the unredacted process/trace rows and full executable bodies.

```sh
python3 -IB read_native.py "$RAW" --output native.json
python3 -IB read_behavior.py "$RAW" > checked-behavior.json
python3 -IB project.py native.json > rebuilt-summary.json
cmp native.json verified-raw.json
cmp checked-behavior.json behavior.json
cmp rebuilt-summary.json summary.json
```
