# Blocking-wait cohort

This directory records the second 32 pairs separately from the first polling cohort. The numerical schedule, candidate and source hashes, cold reference, and performance criteria are in `registration.json`. Run `python3 -IB verify.py` for independent replay of all 128 new clocks, endpoint estimates and both per-direction repeat margins. The full per-direction distributions are in `result.json` and chronological data are in `rows.json`. The regular-file timer uses a SIGALRM watchdog outside `Popen` and unconditional blocking `wait`.
