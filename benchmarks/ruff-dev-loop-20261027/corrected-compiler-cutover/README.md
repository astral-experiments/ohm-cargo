# Metadata upgrade and stale-library reproducer

`evidence-v7a-stage1.tar.gz` contains the corrected compiler results for commit `3a9e8ee19f74e4d0860da3ed60f9bb663332ec19`. It includes 18 compiler graphs, six historical controls and nine SDK loading cases. `evidence-v6.tar.gz` preserves the earlier candidate that still crashed on a legacy ordinary intermediate even though the producer retained its full crate hash.

Each archive contains a README, raw observations and an offline verifier. Extract each archive into its own empty directory and run `python3 -B verify.py` there.
