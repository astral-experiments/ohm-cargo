# Final edit-section file custody

All 226 observed files from the twelve edit-and-repeat pairs amount to 82,660,757 bytes. The source volume, a separate scratch filesystem, and a second host each supplied the same complete SHA-256 inventory. After both additional copies were made durable, a new read of every original also verified its inode, file type, owner, mode, link count, size and three timestamps. Every original remains at its scored location.

The inventories cover the combined twelve-pair record, each individual pair, both host envelopes, the section grant, the operator binding, the three original launcher streams, and all 58 ordinary command records with their stdout and stderr. They also include all four live native traces and tool contracts and all 24 separate behavior checks. Each inventory uses the same logical names so it can be verified without the private workspace paths. Diagnostic payloads and binaries remain with their custodians.

Run `python3 -IB verify.py` to recheck the complete file roster, both replica commitments and the original terminal launcher bytes.
