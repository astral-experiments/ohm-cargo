# Edited test-build instruction counts on Ohm -18

After the diagnostic edit, the fixed stack used 2.058% fewer instructions across Cargo, rustc and Wild while building the test harnesses. All eight pairs favored the stack. The 99.22% rank interval was 1.831% to 2.275%. The two-sided sign p-value was 0.0078125 and the order-conditioned p-value was 0.028571. The independently edited first checkout measured 2.097%. Both workloads built the same 72 test executables.

The first attempt at this second checkout stopped before recording any samples. The fresh run used a predeclared admission which reconstructs both full stock ELF hashes observed in that attempt. DynamoRIO counted the instructions executed by the measured processes. [Registered comparison](../README.md)

Extract the outcome ZIP in an empty directory and run `python3 -I -B detached.py` with Python 3.12. It checks the embedded registration, raw per-process counts, command roster, binary and checkout receipts, paired order and final outcome. [Packet checksums](SHA256SUMS)
