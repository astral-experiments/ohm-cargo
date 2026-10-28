# H5 score transcript compatibility

The published v3c offline receiver expected 24 pair-completion lines on stdout. Its registered score worker also calls the native workspace worker once per slot. Each call prints one unchanged-audit line before the pair-completion message. The actual 72-line transcript is 4,503 bytes, SHA-256 `b443caafd976c1c691a28e271783204473d4593263b29e372ce7d9d7653bb021`. The published offline reader stops at line 121. The physical admission, score and verifier all exited zero. [Published receiver](https://github.com/astral-sh/ohm-cargo/blob/54793ae4effa4ca71b9b0dde1d00a55afaf33946/benchmarks/ruff-dev-loop-20261027/rc17-composed-early-wall-export-v3c/verify.py#L121) · [Registered score worker](https://github.com/astral-sh/ohm-cargo/blob/f8ee28c60e872a090b4600f473b303738be05029/benchmarks/ruff-dev-loop-20261027/rc17-composed-early-wall-plan-v3c/runner.py#L177) · [Native workspace worker](https://github.com/astral-sh/ohm-cargo/blob/23ca620a9ac3e16402d566f23670dc954bf638f7/benchmarks/ruff-dev-loop-20261027/rc17-composed-early-native-workspace-plan/ruff_worker.py#L86)

`verify_compat.py` authenticates the original receiver manifest and source, then replaces one assertion in memory. It reconstructs one audit line for each slot in the registered arm order followed by the numbered pair line. Unit count, fresh count and number of workspace ELF files come from that slot’s saved `unchanged/products.json`. Job counts and their display order come from its ordered physical process records and must agree with the product receipt. The assertion compares the entire transcript, including whitespace and final newline. The original handling of failed or incomplete runs stays in effect. The physical verifier and registered analysis are still called by the original reader.

In every slot the audit reported 619 units, 563 fresh, 110 workspace ELF files, one full rustc, 50 link-only rustcs and 50 Wild links. These lines carry no arm label. The separate slot, Cargo executable, worker roster and clock records establish arm identity. With the corrected check, all 48 clocks, 24 pair checkpoints, product comparisons and the original statistical result agree. The prior four v2 clock files have no role in this replay.

## Replay

Place this component beside the published receiver directory `rc17-composed-early-wall-export-v3c`. Use the same arguments as the published verifier. The directories below are the independently checked-out evidence components, and `RESULT` is the directory holding the terminal packet and previously published input pins.

```sh
python3 -IB verify_compat.py "$RESULT/terminal.json.gz" "$PLAN" "$ORIGINAL_NATIVE" \
    "$RESULT/published-pins.json" "$STOCK_RESULTS" --admission-results "$ADMISSION" \
    --h2-results "$H2_RESULTS"
```

`check.py` replays the original rejection and the successful overlay using those components under their standard sibling names. It checks the compressed terminal packet and pins against their original transport SHA-256s. The negative tests change in-memory copies, recomputing the affected hashed bodies, then run the complete receiver and require an exception at the intended check. The cases include a missing or extra audit, pair-only output, wrong line order or counts, a matching alteration to the product and stdout that disagrees with the real traced jobs, and an altered recorded duration that reaches the downstream clock guard. [Native admission](https://github.com/astral-sh/ohm-cargo/tree/60ff6a54b7506a487313f007d97e144a3bcffaf9/benchmarks/ruff-dev-loop-20261027/rc17-composed-wall-admission-v3c)

```sh
python3 -IB check.py
sha256sum -c SHA256SUMS
```
