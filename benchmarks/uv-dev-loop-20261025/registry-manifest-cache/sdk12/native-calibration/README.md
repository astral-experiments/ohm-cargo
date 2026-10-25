# Native A/A calibration: closed before candidate comparison

Both preregistered A/A noise gates failed. **No native candidate comparison ran; the registry-manifest candidate's elapsed-time effect remains unknown.** A and B are labels for two independent baseline-Cargo banks, both using binary `4f7104d7aaf0dec561d8e1457d136f02e0dcdd479fe0bb0957724fba46060306`.

| Machine | Geometric label bias | 99% interval | Full interval width | A/A gate |
|---|---:|---:|---:|---|
| host-1 | +0.803238% | -11.733760% to +13.383614% | 25.117374 percentage points | Fail |
| host-2 | +4.258626% | -7.089160% to +13.018231% | 20.107391 percentage points | Fail |

Each machine had eight fixed balanced pairs, with inverse orders on the second machine. The A/A rule required absolute geometric label bias <=0.35%, a 99% interval containing zero, and full interval width <=1.5 percentage points. Both bias and width fail on each machine; both intervals contain zero. There is no pooled estimate, extension, replacement or native A/B result. Exact sign tests and order strata are retained in the per-host summaries; the sign test was not an A/A gate. Generic inherited `baseline`/`candidate` statistic keys mean labels A/B here, **not different binaries**.

The measured command was plain `cargo -Zohm-defaults=yes check --locked --offline -j 8` on the pinned uv source and SDK12. The fixed non-doc comment edit preserves Rust tokens and source positions. The timer spans Popen through the normal Cargo wait; positive descendant drain is required afterward before path reuse. Both original full raw/output/quietness/restoration gates passed before any calibration duration was read. All 32 integer records were checked before either independent statistic. The two excluded operational A/A rehearsals discarded individual timer returns; their aggregate-only scheduling evidence is not part of these samples.

Run the standalone replay with Python 3.11 or later:

```sh
python3 -I -B reproduce.py --output /tmp/registry-native-aa-replay.json
```

This verifies all public file hashes, the 32 original two-field elapsed JSON files, CSV labels/order, fixed seeds 20261025251/20261025252, 200,000 paired bootstrap resamples, and byte-for-byte equality of the decoded numerical results with the accepted summaries and decision. Eight numerical/gate function bodies are extracted byte-identically from the frozen source. `controls/` retains all 25 collector/validator sources with only declared private-path, hostname and infrastructure-service literal substitutions; it is an archival source audit, not an executable hosted fixture.

`provenance.json` binds the complete private raw/restoration custody and original decision by SHA-256. The original decision and summaries remain private and unchanged; only host labels are pseudonymized in the public copies. Complete private environments, traces, process rows and output copies are retained but excluded from this small packet. Portable numerical replay does not independently establish those omitted host/output facts. The decision's `withhold_PR: false` means no replicated A/B regression was observed because A/B never ran; it is not publication authority or evidence of no regression. Warm/cold instruction results remain separate.
