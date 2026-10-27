# Detecting redundant native work after real Ty and Ruff formatter edits

The pinned historic changes cover deduplicating consecutive invalid-argument diagnostics in Ty and formatting a comment that starts with a tab in Ruff. Both full patches applied in reverse at the enrolled Ruff revision in a disposable index before observing either native outcome. The investigation checks both directions of both complete workspace commands with Cargo #254 and Rust #233.

The question is whether all the real inputs of a downstream compiler or linker stayed byte-identical while the tool still ran. Equal output sections alone do not qualify a job. See plan.json for selected commits, workload, limits and frozen identities, and selection.json for the candidate search. These are structural observations; this packet enrolls no elapsed-time endpoint.
