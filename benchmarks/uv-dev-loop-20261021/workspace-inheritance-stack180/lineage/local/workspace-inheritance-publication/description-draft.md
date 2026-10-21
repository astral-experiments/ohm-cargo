Large workspaces cloned the full inherited dependency map for each member. Share that immutable map through `Arc` so cloning inheritance settings only increments a reference count. The selected dependency is still cloned before applying member-specific features and path rebasing.

Validation: all 28 existing inheritance tests passed, and Linux/macOS CI passed on the exact source commit.

Performance results and immutable evidence links will be added only after the frozen instruction-count and native phases finish and pass independent review. Baseline: exact PR180; benchmark: unchanged pinned uv.
