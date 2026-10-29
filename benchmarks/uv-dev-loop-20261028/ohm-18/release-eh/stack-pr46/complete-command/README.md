# Edited uv test compilation on Wild #46

Both arms use the same -18 Cargo and rustc. The linker control is Wild #46 at `db821991bd2931dd83e59f236149340ddfc2b427`. Each full-workspace `cargo test --no-run --locked --offline -j8` follows a genuine edit in the uv library. Each counted command includes one Cargo process, six rustc processes and five Wild processes and produces 72 test executables.

| Checkout | Median instruction saving | 99.22% paired interval | Pairs improved | Raw / canonical product matches |
|---|---:|---:|---:|---:|
| Initial | 0.213% | 0.086% to 0.324% | 8/8 | 586/592 and 592/592 |
| Replica | 0.214% | 0.187% to 0.311% | 8/8 | 587/592 and 592/592 |

Elapsed times were outside this experiment. The archive includes the command logs and counts, source trees and build identities, physical return receipts, executable and product checks, the separately retained rejected admission, and the standard-library-only verifier.

[Complete archive](complete-command-evidence.zip) The assembled archive SHA-256 is `e51938c7068704b3cb20354c517166337c8c384b434c026fb493a13269655fc4`. Extract it in an empty directory and run `python3 -I -B verify-complete.py`. [Detailed results and artifact checks](FINAL-EVIDENCE.md)
