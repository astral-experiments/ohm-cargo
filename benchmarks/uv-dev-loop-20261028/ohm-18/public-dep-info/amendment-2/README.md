# Physical target directory assignment

Each Cargo driver runs on all four physical target directories at the same canonical path. The initial checkout assigns the four directories to execution ranks in preparation order. The replica rotates that assignment by two positions. Every driver uses each directory 864 times on the first checkout and 240 times on the replica. Directory assignment depends only on rank and checkout, so reassigning the two treatment labels in the original conditional randomization test leaves the physical directory at each slot fixed.

The runner records the device and inode before and after each ordinary Cargo command, outside its elapsed-time interval. The separate bank verifier checks every assignment against its prepared directory, rejects missing or swapped rows and checks exact balance. The source, edits, toolchain inputs, training, instruction-count phases, arm order, sample sizes and statistical test are identical to the preceding registration. The three registrations were sealed before building the two new Cargo drivers or collecting candidate observations.

Unpack the archive and run `python3 -I -B verify-registration.py` with Python 3.11 or later. It verifies the frozen files and independently reconstructs the assignment for all 17,664 timed commands. The original source-borrow repair remains in the preceding archive. [Three registrations and verifier](complete-command-registration-v3.zip) · [Source correction](../amendment-1/)

The delta archive includes the two complete protocol directories, unified diff and 35 synthetic negative controls. The physical coordinator is provided alongside it. [Verified protocol diff](bank-design-delta.zip) · [Physical coordinator](segment.py)
