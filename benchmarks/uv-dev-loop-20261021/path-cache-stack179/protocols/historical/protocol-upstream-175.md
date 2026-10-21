# Upstream change and confirmation baseline

Recorded 2026-10-21 at approximately 03:04 UTC, before inspecting completed
path-cache exploratory instruction results or native confirmation effects.

PR175 (`efc8b51502f8a8d1fe76997dc984481edde2740e`, based on pinned Cargo
`5e5d271d763d7beb38b48755e22bd59e93f02b97`) was opened by another task at
02:46 UTC. It skips output dep-info work for roots with no uplifted destination.
The exact one-file patch is saved as `work/production-build/pr175.patch`.

This external change affects the usefulness of proposed optimizations:

- Drop the unmeasured output-depinfo HashSet/sort candidate as overlapping.
- Finish the already running eight-pair path-cache instruction exploration and
  thirty-pair native check confirmation unchanged. Preserve every observation.
- Hold the not-yet-started path-cache test-build native batch. Its eventual
  usefulness depends on whether the gain survives PR175.
- Prioritize the build-output identity-remap optimization, which targets a
  separate parser. Its implementation remains frozen.

The original non-LTO build-output binaries may be used for the eight-pair
exploratory instruction screen against pinned Cargo, with two warmup pairs.
The independent twelve-pair instruction confirmation will compare PR175-only
against PR175 plus the unchanged candidate using matched release-like builds.
These use all-static/ohm-defaults, ThinLTO, one codegen unit, and no PGO. Both
variants are built at the same physical source and target paths, on the same
host, with the same compiler and environment. They are not represented as
identical to published PGO binaries.

Confirmation preserves the original gate: at least 1% fewer Cargo instructions,
a positive 99% paired bootstrap interval, exact two-sided sign-test p <= 0.01,
and positive estimates in both execution orders. Exploratory and confirmation
samples are not pooled, especially across build settings or baselines.

Native confirmation on the PR175 baseline uses thirty randomized paired groups
of eight fresh invocations, two warmup pairs, and the frozen repeated runner.
The group is the statistical unit. All raw subruns remain available, including
failed or non-fresh invocations; those invalidate the relevant batch rather
than being silently removed. Record the actual Cargo/Ohm/uv hashes and source
patches in each manifest. Validate the second workflow before publication.

No path-cache PR will be justified solely by the old baseline if PR175 removes
its useful effect. Existing failed or inconclusive pilots remain in the record.
