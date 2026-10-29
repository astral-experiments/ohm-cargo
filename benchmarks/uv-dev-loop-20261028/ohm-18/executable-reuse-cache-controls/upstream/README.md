# Ohm Cargo source overlap for executable reuse

The October 29 inventory covered 55 released Cargo pins, 287 branch heads and 231 posted PR heads. They identify 319 distinct commits. Of those, 306 contain a Cargo compiler implementation under the modern or historical Cargo path. The other 13 belong to benchmark-evidence branches.

The 306 implementations reduce to 114 distinct Git blobs, whose original Git hashes were checked against their bytes. In 89, the self-library reuse helper explicitly rejects any target that is not an integration test. The other 25 lack the helper. The proposed change itself passed the positive control for ordinary binary support. The existing release's behavior was also checked by executing both binaries on the same source edit.

The closest prior PRs implement the integration-test path and its existing checks. #139 retains that path under bundled Wild. #152 reuses an already-built library in check mode. #161 handles unused dev dependencies for targeted library tests. None of these implements the proposed ordinary binary build and binary test-harness path. [Original integration support](https://github.com/astral-sh/ohm-cargo/pull/72) · [Broader integration reuse](https://github.com/astral-sh/ohm-cargo/pull/73) · [Bundled Wild](https://github.com/astral-sh/ohm-cargo/pull/139) · [Check-mode library reuse](https://github.com/astral-sh/ohm-cargo/pull/152) · [Targeted library tests](https://github.com/astral-sh/ohm-cargo/pull/161)

`verified.json` maps every head to its Git blob, the scope of its self-library helper and its lines. `nearby.json` includes the seven closest PRs. The census checks the two owning source paths and related PRs. The live Ohm monitor continues to track new revisions and feedback separately.
