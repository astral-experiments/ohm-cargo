# Retired instructions for a full Ruff CLI build after switching branches

With the opt-in in Rust #274 enabled, returning to Ruff's two previously built checkouts used 241.46 billion retired user-mode instructions. The default used 1,691.45 billion. The median paired ratio was 7.00508× across six independent Linux hosts. The exact 96.875% interval was 7.00330–7.00598×. All six exceeded the registered 2× threshold. The first switch cost 6.1% more instructions, the unchanged build stayed level and the seven commands together used 26.4% fewer instructions. [Rust #274](https://github.com/astral-experiments/ohm-rust/pull/274) · [Registered workflow](https://github.com/astral-experiments/ohm/tree/23685581114abfed1227fb7514bbc0ad934a1ecd/scripts/branch-return-pmu) · [Results for every visit](tables.md)

Each host built Ruff revisions `b5dba861` and `7b13f01b` using the same offline Cargo command. The 169-path change includes a real AST layout change. All seven commands were metered, including rejection of a type error and the subsequent repair. Separate controls checked the diagnostic, compared the full CLI and typed AST-reader executables with clean builds, and exercised changing native libraries. F off and F on use the same compiler. K on adds compression of eligible incremental object files. The six hosts exercised all six orders. Each retired-instruction counter covered Cargo and its descendants. [Source-built compilers and native controls](https://github.com/astral-experiments/ohm/tree/d4a51f5df64991bf76a2ca20bd743d0a89fc545c/scripts/branch-return-source/result) · [Six-host confirmation](https://github.com/astral-experiments/ohm/actions/runs/41222947202)

```sh
cargo +ohm build -p ruff --bin ruff --locked --offline -j4 --message-format=json
```

The additional object compression saved 132.2 MiB on the first switch relative to F on and used 6.55% more instructions on the two returns. Two independently registered groups of 12 other hosts compared that compiler with its own cache enabled and disabled. They measured 6.57428× and 6.57443× on the two returns. The median maximum allocation sampled at command exits rose from 2.433 to 2.686 GiB. The packed compiler is a separate prototype. The complete results preserve the negative edit and repair and report target and build directories with hardlinked inodes counted once. [First 12 hosts](https://github.com/astral-experiments/ohm/actions/runs/41219513694) · [Second 12 hosts](https://github.com/astral-experiments/ohm/actions/runs/41219530573)

## Recheck the counts

From this directory, regenerate the six-host tables without a compiler or network access.

```sh
sha256sum --check SHA256SUMS
python3 -IB score.py direct.json > /tmp/ohm-ruff-cli-direct-tables.md
cmp tables.md /tmp/ohm-ruff-cli-direct-tables.md
```

The 24-host archive includes a separate reader, host receipts, all 336 original counter records, original GitHub archive identities, and instructions for replaying the original binaries. To recalculate both intervals offline, run the following from this directory.

```sh
review=$(mktemp -d)
tar -xzf packed-confirmation.tar.gz -C "$review"
(
  cd "$review" || exit
  sha256sum --check CONTENTS.sha256
  python3 -IB confirm.py score results/c1-raw.json results/c2-raw.json --out checked.json
  cmp checked.json results/decision.json
)
```

## Original six host archives

The raw GitHub artifacts contain the hardware calibration, native executable bytes, Cargo verdicts, and filesystem allocation records used to reconstruct `direct.json`.

| Position | Job | Artifact | Archive SHA-256 |
| --- | --- | --- | --- |
| 01 | [124601110954](https://github.com/astral-experiments/ohm/actions/runs/41222947202/job/124601110954) | [13051182374](https://github.com/astral-experiments/ohm/actions/runs/41222947202/artifacts/13051182374) | `956ffdc0359ba81c8401368c3f67f80009b1a475031cccdb528bf98c1acc9ad0` |
| 02 | [124601111061](https://github.com/astral-experiments/ohm/actions/runs/41222947202/job/124601111061) | [13051902158](https://github.com/astral-experiments/ohm/actions/runs/41222947202/artifacts/13051902158) | `7ccf8577429a4c6893aceccf1da765a82b0e95141b4a003edf09e9227d6f3bdb` |
| 03 | [124601111031](https://github.com/astral-experiments/ohm/actions/runs/41222947202/job/124601111031) | [13052497120](https://github.com/astral-experiments/ohm/actions/runs/41222947202/artifacts/13052497120) | `9bf0e08afec3f7e8677390900668d88de2f7e2aaa5b04a733b4837a1eaad15d6` |
| 04 | [124601111014](https://github.com/astral-experiments/ohm/actions/runs/41222947202/job/124601111014) | [13052502294](https://github.com/astral-experiments/ohm/actions/runs/41222947202/artifacts/13052502294) | `6582d429d095aceff222dc9229ad84d25d52d921d31c5b2ce768c264b19ac522` |
| 05 | [124601111140](https://github.com/astral-experiments/ohm/actions/runs/41222947202/job/124601111140) | [13053781208](https://github.com/astral-experiments/ohm/actions/runs/41222947202/artifacts/13053781208) | `907278a5eb6c5a89a0120afc4aca907551b1f2362e6844fca317da0e0e421530` |
| 06 | [124601110964](https://github.com/astral-experiments/ohm/actions/runs/41222947202/job/124601110964) | [13053557109](https://github.com/astral-experiments/ohm/actions/runs/41222947202/artifacts/13053557109) | `2f5bb1dbac10ee2aa3b1bba3ab450455cc1684ba41cc9d56702646295a8a802c` |
