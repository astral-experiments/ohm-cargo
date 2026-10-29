# Cargo relink manifest write through a final symlink

An ordinary Cargo library unit test created an independent sample manifest, then placed a symbolic link at the cache record path pointing to that sample. It requested a write of a different checked relink manifest. The test asserts that the sample remains byte-identical and the cache record can be reopened with the new unused-extern value.

The extended test is the only source difference from parent a8f0c9aa in its detached control. It failed at the first post-write content assertion. The parent replaced the sample's 265 original bytes with 231 serialized manifest bytes. The input checksum stayed the same and the proof checksum changed. Commit 5394ce88 passed the same test with its byte-preserving no-follow writer. All 8 relink-cache tests and all 3 adjacent atomic utility tests passed on Linux.

The separately built uninstrumented developer Cargo enabled the ohm-defaults feature. It reports commit 5394ce8817e224971230b80a9066cc28d504ff94. Both the unit-test names and the binary, source and original output digests are recorded in result.json. Run python3 -IB verify.py to check this packet.
