# Cargo dependency-file source correction before measurement

The Cargo utility reader accepts a borrowed path. The first proposed source passed a temporary `PathBuf` by value. The corrected source adds a single `&` at that call. This call sits outside the previously measured writer loop. [Complete one-character source change](source-correction.patch)

The original registration and its 70 source inputs are preserved. Both versions specify the same uv revision, two behavioral edits, four Cargo arms, training procedure, 192 counted builds, 17,664 ordinary builds, candidate comparisons, sample order and statistical gates. The new candidate tree is `7fd9d2ee894d5f0c6369e4a75df5380c24ded6b0`. At the time of this correction, neither study had built a new Cargo driver, observed a complete-command candidate count or recorded a candidate elapsed time.

Unpack the archive into an empty directory and run `python3 -I -B verify-registration.py`. It verifies both registrations, the byte hashes of their constituent inputs and the shared comparison design. [Original and corrected registrations](complete-command-registration-v2.zip)
