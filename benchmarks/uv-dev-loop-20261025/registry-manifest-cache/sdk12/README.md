# Registry manifest cache on the uv development loop

The benchmark runs `cargo -Zohm-defaults=yes check --locked --offline -j 8` on the SDK12 uv fixture after a reversible source comment edit. The build target is already warm. Only the registry manifest cache changes between the repeated-check and first-use studies. Both versions of Cargo were built from source with the same release settings. Each fixed block uses eight balanced, paired comparisons on a dedicated VM.

| Cargo-parent instruction result | Machine 1 | Machine 2 |
| --- | ---: | ---: |
| Repeated check, reduction and 99% interval | 5.266% (5.095–5.345%) | 5.394% (5.280–5.605%) |
| First use, increase and 99% interval | 18.073% (17.879–18.174%) | 18.211% (18.132–18.391%) |
| Additional warm checks needed to recover the first-use cost | 3.435 (3.370–3.552) | 3.373 (3.237–3.459) |

All eight pairs agreed in direction in each block. The two-sided sign-test p-value was 0.0078125 per block. The break-even estimate divides the mean paired first-use cost by the mean paired repeated-check saving on the same machine. Four additional warm checks recover the measured instruction cost on either machine.

The candidate binary grew by 1,122,888 bytes. On each machine a separate first-use trace recorded 847,429 logical bytes written in 470 successful commits. There were 25 replacements, leaving 445 committed slots with 803,161 bytes. The baseline recorded zero cache writes. The traces establish syscall-level byte counts. Physical device traffic was unmeasured. The four traced commands passed context, diagnostic and restoration checks. Their collector stopped before capturing the dirty artifact snapshot. All 64 instruction-study calls passed their full output checks.

The separate whole-command timing calibration compared two independent baseline states. The A/A label differences were 0.803% and 4.259%, with 99% intervals of −11.734% to 13.384% and −7.089% to 13.018%. Both machines exceeded the fixed bias and interval-width limits. The study stopped at calibration, leaving the candidate’s elapsed-time effect unknown.

## Replay

Run these commands from this directory with Python 3.11 or newer. The first two commands replay all 64 complete instruction profiles. The third reproduces the payback intervals. The fourth replays the four syscall traces and the fifth reproduces the timing calibration from all 32 integer-nanosecond observations.

```sh
(cd check && python3 -I -S -B reproduce.py)
(cd first-use-check && python3 -I -S -B reproduce.py)
(cd first-use-check && python3 -I -S -B break_even.py --warm ../check --cold .)
python3 -I -S -B replay-writes.py
(cd native-calibration && python3 -I -S -B reproduce.py)
```

The write-trace replay makes a temporary copy with the recorded file permissions so it works across checkout umasks. Its manifest verifies every file in that copy. Each study directory includes its protocol, validation scope, and retained evidence.
