use super::{
    CargoResult, CliUnstable, IndexSummary, InternedString, PackageId, SourceId, Summary, Version,
};
use crate::workspace::summary::PackedIndexSummary;

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
