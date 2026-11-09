use super::{
    CargoResult, CliUnstable, IndexSummary, InternedString, PackageId, SourceId, Summary, Version,
};
use crate::workspace::summary::PackedIndexSummary;

use std::sync::{Arc, Mutex};
use std::thread::{self, ThreadId};

type SharedIndex = Arc<Mutex<SelectedIndex>>;

/// A Cargo context may be shared between threads. Each synchronous resolver owns its
/// registry queries on one thread, including while polling its local registry futures.
#[derive(Default, Debug)]
pub(crate) struct SelectedIndexes(Mutex<rustc_hash::FxHashMap<ThreadId, SharedIndex>>);

impl SelectedIndexes {
    pub(crate) fn current(&self) -> Option<SharedIndex> {
        self.0.lock().unwrap().get(&thread::current().id()).cloned()
    }

    pub(crate) fn scoped<T>(&self, enabled: bool, run: impl FnOnce() -> T) -> T {
        let owner = thread::current().id();
        let previous = if enabled {
            self.0.lock().unwrap().insert(owner, Arc::default())
        } else {
            self.0.lock().unwrap().remove(&owner)
        };
        if !enabled && previous.is_none() {
            return run();
        }
        struct Restore<'a> {
            indexes: &'a SelectedIndexes,
            owner: ThreadId,
            previous: Option<SharedIndex>,
        }
        impl Drop for Restore<'_> {
            fn drop(&mut self) {
                let mut scopes = self.indexes.0.lock().unwrap();
                if let Some(previous) = self.previous.take() {
                    scopes.insert(self.owner, previous);
                } else {
                    scopes.remove(&self.owner);
                }
            }
        }
        let _restore = Restore {
            indexes: self,
            owner,
            previous,
        };
        run()
    }
}

/// Decoded records from a previous resolution. The digest covers the entire raw index row,
/// including its schema, yanked status and checksum, before source replacement or locking.
#[derive(Debug, Default, serde::Serialize, serde::Deserialize)]
pub(crate) struct SelectedIndex {
    variants: rustc_hash::FxHashMap<(u64, [u8; 32]), crate::workspace::summary::PackedIndexSummary>,
    #[serde(skip)]
    reused: Vec<((u64, [u8; 32]), Summary)>,
    #[serde(skip)]
    seen: rustc_hash::FxHashMap<(InternedString, Version), Option<(u64, [u8; 32])>>,
}

impl SelectedIndex {
    pub(crate) fn observed(&self, id: PackageId) -> Option<(u64, [u8; 32])> {
        self.seen
            .get(&(id.name(), id.version().clone()))
            .copied()
            .flatten()
    }

    pub(crate) fn finish_recording(&mut self) {
        // A later row can reject a replay after earlier rows have already been decoded.
        // Keep those rows when replacing the previous selection.
        for (key, summary) in self.reused.drain(..) {
            if let Some(packed) = PackedIndexSummary::pack(&summary) {
                self.variants.insert(key, packed);
            }
        }
    }

    pub(super) fn parse(
        &mut self,
        line: &[u8],
        source: SourceId,
        unstable: &CliUnstable,
    ) -> CargoResult<IndexSummary> {
        use std::hash::{Hash as _, Hasher};
        let mut hash = crate::util::StableHasher::new();
        source.hash(&mut hash);
        let key = (Hasher::finish(&hash), *blake3::hash(line).as_bytes());
        let summary = if let Some(summary) = self
            .variants
            .remove(&key)
            .and_then(|summary| summary.unpack(source))
        {
            self.reused.push((key, summary.clone()));
            IndexSummary::Candidate(summary)
        } else {
            let summary = IndexSummary::parse(line, source, unstable)?;
            if let IndexSummary::Candidate(candidate) = &summary
                && let Some(packed) = PackedIndexSummary::pack(candidate)
            {
                self.variants.insert(key, packed);
            }
            summary
        };
        if let IndexSummary::Candidate(candidate) = &summary {
            let id = candidate.package_id();
            let observed = self
                .seen
                .entry((id.name(), id.version().clone()))
                .or_insert(Some(key));
            if *observed != Some(key) {
                *observed = None;
            }
        }
        Ok(summary)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn selected_index_scopes_restore_and_isolate_resolvers() {
        let scopes = SelectedIndexes::default();
        scopes.scoped(true, || {
            let outer = scopes.current().unwrap();
            std::thread::scope(|threads| {
                threads.spawn(|| {
                    assert!(scopes.current().is_none());
                    scopes.scoped(true, || {
                        assert!(!Arc::ptr_eq(&outer, &scopes.current().unwrap()));
                    });
                });
                assert!(
                    std::panic::catch_unwind(|| scopes.scoped(false, || {
                        assert!(scopes.current().is_none());
                        panic!("resolve aborted");
                    }))
                    .is_err()
                );
            });
            assert!(Arc::ptr_eq(&outer, &scopes.current().unwrap()));
        });
        assert!(scopes.current().is_none());
    }
}
