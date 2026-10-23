# Why this changes real build work

Before the change, each prepared compiler command asks `lib_search_paths` to walk its dependency Unit DAG into a `BTreeMap`, obtain dependency directories, and sort the resulting paths. Sibling target commands can repeat this work with the same dependencies. It occurs during dependency-argument construction in the build phase, including ordinary `cargo test` builds.

The patch adds one cache to `CompilationFiles`: an ordered `Vec<Unit>` key mapped to the sorted dependency `-L` prefix. The key contains the exact direct dependency Units in their original order, excluding custom-build targets. Unit equality/hashing uses interned identity; constructing/hashing the whole key is still O(number of direct dependencies). A miss executes the original traversal and sort. A hit clones the saved argument vector. The root-specific host-directory suffix is appended on every call outside the cache.

This boundary preserves details that a path-set cache would lose. Distinct Units may yield duplicate paths; these duplicates and the original ordering remain. A proc-macro dependency contributes its directory but terminates traversal into its own dependencies. Custom-build targets remain pruned. Native flags, `--extern` arguments, build-script outputs, environment preparation, and trust/cache eligibility are not memoized by this change.

The graph and directory decisions are fixed for the lifetime of the finalized `CompilationFiles` used by command preparation. The shared-context fallback can change directory naming during preparation, so it clears this cache beside the existing Unit-directory caches. Root compile kind and host suffix are handled after prefix reuse. Cache borrows do not recurse into the cache itself.

A source-derived grouping of the eighteen uv commands prepared in the motivating dirty build suggested five distinct direct-dependency groups. That is a reuse hypothesis, not a measured cache-hit rate: no exact retained Unit graph established all eighteen keys. The accepted paired Cargo totals measure the complete parent process; they do not convert this grouping into a whole-build time estimate.

The added cost is one retained key/prefix per distinct dependency list until `CompilationFiles` drops, O(D) key work, and copying the returned prefix bytes. Memory effects were not measured. The miss path deliberately retains the existing `BTreeMap` and path sort; no earlier map/sort/display candidate is combined.

The new actual-argv fixture checks sibling integration targets, native versus explicit host-triple builds, different root host suffixes, proc-macro cutoff, custom-build pruning, and a retained native-search flag. Four selectors passed on both stock Rust 1.99.0 and Ohm 1.99.0-6. Duplicate-path retention and fallback clearing also received source review; the fixture does not force every fallback or foreign-target condition. See [correctness.json](correctness.json) for the exact scope.
