# Independent Ruff scheduler wall result

Both arms ran the registered whole Cargo command on a 32-CPU Linux machine using the same released rustc and stock Wild, the same 8 requested Cargo jobs, and the original Ruff tree 93526150df078af7dd8fc4226cdcc469539d2001. A is 235f9228651b74c591e6f62cae4c9b761448dd2d. B is 4b0751af97bfa22204a013d0d1f0707382b0df52. Only Cargo’s choice among already-ready, equal-priority native test jobs differs. It estimates work from the size of the previous executable.

The 96 adjacent pairs yielded median A 9.093 s and B 10.267 s. The registered geometric mean paired reduction was -11.87%, with a blocked bootstrap 95% interval [-15.86%, -8.15%]. B was faster in 28/96 pairs. Two-sided sign-test p = 5.45915e-05. Batch reductions were -14.23% and -9.56%.

The independent plain-output comparison of 16 adjacent pairs yielded a geometric-mean paired reduction of -18.14%. The registered independent-machine gate did not pass. The second machine and the edited workflow have their own gates.

Each of the 192 typed Cargo commands returned 0, emitted 619 compiler artifact records, and marked 563 fresh. The 32 plain-output commands returned 0. Separately traced commands before, between and after the timed sets checked the compiler and native tools, all 50 output files, and the two notebook tests. The typed and plain clocks excluded ptrace, storage validation and test execution.

Each batch used independent writable states copied from a byte-verified, quiescent warmed baseline and mounted at matching ordinary paths. The unrevised Rust and GCC command comparison covers all flags and persistent names. Exactly three ephemeral Rust or GCC operands were validated independently by their contents and roles. ELF validation retained complete raw digests as well as the narrow stock-linker fields. Host and cgroup counters, per-run stdout/stderr digests and every pair in the prescribed order are included.

Run `sha256sum -c SHA256SUMS` and `python3 -IB verify.py` to replay the complete registered inference.
