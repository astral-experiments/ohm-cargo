use crate::util::data_structures::HashSet;
use std::cmp::Ordering;
use std::fmt::{self, Formatter};
use std::hash;
use std::hash::Hash;
use std::path::Path;
use std::ptr;
use std::sync::Mutex;
use std::sync::OnceLock;

use serde::de;
use serde::ser;

use crate::util::CargoResult;
use crate::util::interning::InternedString;
use crate::workspace::PackageIdSpec;
use crate::workspace::SourceId;

static PACKAGE_ID_CACHE: OnceLock<Mutex<HashSet<&'static PackageIdInner>>> = OnceLock::new();

/// Identifier for a specific version of a package in a specific source.
#[derive(Clone, Copy, Eq)]
pub struct PackageId {
    inner: &'static PackageIdInner,
}

#[derive(PartialOrd, Eq, Ord)]
struct PackageIdInner {
    name: InternedString,
    version: semver::Version,
    source_id: SourceId,
}

// Custom equality that uses full equality of SourceId, rather than its custom equality.
//
// The `build` part of the version is usually ignored (like a "comment").
// However, there are some cases where it is important. The download path from
// a registry includes the build metadata, and Cargo uses PackageIds for
// creating download paths. Including it here prevents the PackageId interner
// from getting poisoned with PackageIds where that build metadata is missing.
impl PartialEq for PackageIdInner {
    fn eq(&self, other: &Self) -> bool {
        self.name == other.name
            && self.version == other.version
            && self.source_id.full_eq(other.source_id)
    }
}

// Custom hash that is coherent with the custom equality above.
impl Hash for PackageIdInner {
    fn hash<S: hash::Hasher>(&self, into: &mut S) {
        self.name.hash(into);
        self.version.hash(into);
        self.source_id.full_hash(into);
    }
}

impl ser::Serialize for PackageId {
    fn serialize<S>(&self, s: S) -> Result<S::Ok, S::Error>
    where
        S: ser::Serializer,
    {
        s.collect_str(&format_args!(
            "{} {} ({})",
            self.inner.name,
            self.inner.version,
            self.inner.source_id.as_url()
        ))
    }
}

impl<'de> de::Deserialize<'de> for PackageId {
    fn deserialize<D>(d: D) -> Result<PackageId, D::Error>
    where
        D: de::Deserializer<'de>,
    {
        let string = String::deserialize(d)?;

        let (field, rest) = string
            .split_once(' ')
            .ok_or_else(|| de::Error::custom("invalid serialized PackageId"))?;
        let name = field.into();

        let (field, rest) = rest
            .split_once(' ')
            .ok_or_else(|| de::Error::custom("invalid serialized PackageId"))?;
        let version = field.parse().map_err(de::Error::custom)?;

        let url =
            strip_parens(rest).ok_or_else(|| de::Error::custom("invalid serialized PackageId"))?;
        let source_id = SourceId::from_url(url).map_err(de::Error::custom)?;

        Ok(PackageId::new(name, version, source_id))
    }
}

fn strip_parens(value: &str) -> Option<&str> {
    let value = value.strip_prefix('(')?;
    let value = value.strip_suffix(')')?;
    Some(value)
}

impl PartialOrd for PackageId {
    #[inline]
    fn partial_cmp(&self, other: &Self) -> Option<Ordering> {
        Some(self.cmp(other))
    }
}

impl Ord for PackageId {
    #[inline]
    fn cmp(&self, other: &Self) -> Ordering {
        if ptr::eq(self.inner, other.inner) {
            return Ordering::Equal;
        }
        self.inner.cmp(other.inner)
    }
}

impl PartialEq for PackageId {
    fn eq(&self, other: &PackageId) -> bool {
        if ptr::eq(self.inner, other.inner) {
            return true;
        }
        // This is here so that PackageId uses SourceId's and Version's idea
        // of equality. PackageIdInner uses a more exact notion of equality.
        self.inner.name == other.inner.name
            && self.inner.version == other.inner.version
            && self.inner.source_id == other.inner.source_id
    }
}

impl Hash for PackageId {
    fn hash<S: hash::Hasher>(&self, state: &mut S) {
        // This is here (instead of derived) so that PackageId uses SourceId's
        // and Version's idea of equality. PackageIdInner uses a more exact
        // notion of hashing.
        self.inner.name.hash(state);
        self.inner.version.hash(state);
        self.inner.source_id.hash(state);
    }
}

impl PackageId {
    pub fn try_new(
        name: impl Into<InternedString>,
        version: &str,
        sid: SourceId,
    ) -> CargoResult<PackageId> {
        let v = version.parse()?;
        Ok(PackageId::new(name.into(), v, sid))
    }

    pub fn new(name: InternedString, version: semver::Version, source_id: SourceId) -> PackageId {
        let inner = PackageIdInner {
            name,
            version,
            source_id,
        };
        let mut cache = PACKAGE_ID_CACHE
            .get_or_init(|| Default::default())
            .lock()
            .unwrap();
        let inner = cache.get(&inner).cloned().unwrap_or_else(|| {
            let inner = Box::leak(Box::new(inner));
            cache.insert(inner);
            inner
        });
        PackageId { inner }
    }

    pub fn name(self) -> InternedString {
        self.inner.name
    }
    pub fn version(self) -> &'static semver::Version {
        &self.inner.version
    }
    pub fn source_id(self) -> SourceId {
        self.inner.source_id
    }

    pub fn with_source_id(self, source: SourceId) -> PackageId {
        PackageId::new(self.inner.name, self.inner.version.clone(), source)
    }

    pub fn map_source(self, to_replace: SourceId, replace_with: SourceId) -> Self {
        if self.source_id() == to_replace {
            self.with_source_id(replace_with)
        } else {
            self
        }
    }

    /// Returns a value that implements a "stable" hashable value.
    ///
    /// Stable hashing removes the path prefix of the workspace from path
    /// packages. This helps with reproducible builds, since this hash is part
    /// of the symbol metadata, and we don't want the absolute path where the
    /// build is performed to affect the binary output.
    pub fn stable_hash(self, workspace: &Path) -> PackageIdStableHash<'_> {
        PackageIdStableHash(self, workspace)
    }

    /// Filename of the `.crate` tarball, e.g., `once_cell-1.18.0.crate`.
    pub fn tarball_name(&self) -> String {
        format!("{}-{}.crate", self.name(), self.version())
    }

    /// Convert a `PackageId` to a `PackageIdSpec`, which will have both the `PartialVersion` and `Url`
    /// fields filled in.
    pub fn to_spec(&self) -> PackageIdSpec {
        PackageIdSpec::new(String::from(self.name().as_str()))
            .with_version(self.version().clone().into())
            .with_url(self.source_id().url().clone())
            .with_kind(self.source_id().kind().clone())
    }
}

pub struct PackageIdStableHash<'a>(PackageId, &'a Path);

impl<'a> Hash for PackageIdStableHash<'a> {
    fn hash<S: hash::Hasher>(&self, state: &mut S) {
        self.0.inner.name.hash(state);
        self.0.inner.version.hash(state);
        self.0.inner.source_id.stable_hash(self.1, state);
    }
}

impl fmt::Display for PackageId {
    fn fmt(&self, f: &mut Formatter<'_>) -> fmt::Result {
        write!(f, "{} v{}", self.inner.name, self.inner.version)?;

        if !self.inner.source_id.is_crates_io() {
            write!(f, " ({})", self.inner.source_id)?;
        }

        Ok(())
    }
}

impl fmt::Debug for PackageId {
    fn fmt(&self, f: &mut Formatter<'_>) -> fmt::Result {
        f.debug_struct("PackageId")
            .field("name", &self.inner.name)
            .field("version", &self.inner.version.to_string())
            .field("source", &self.inner.source_id.to_string())
            .finish()
    }
}

impl fmt::Debug for PackageIdInner {
    fn fmt(&self, f: &mut Formatter<'_>) -> fmt::Result {
        f.debug_struct("PackageIdInner")
            .field("name", &self.name)
            .field("version", &self.version.to_string())
            .field("source", &self.source_id.to_string())
            .finish()
    }
}

#[cfg(test)]
mod tests {
    use super::PackageId;
    use crate::sources::CRATES_IO_INDEX;
    use crate::util::IntoUrl;
    use crate::workspace::{GitReference, SourceId};
    use std::cmp::Ordering;
    use std::collections::BTreeSet;
    use std::collections::hash_map::DefaultHasher;
    use std::hash::{Hash, Hasher};
    use std::ptr;

    #[test]
    fn invalid_version_handled_nicely() {
        let loc = CRATES_IO_INDEX.into_url().unwrap();
        let repo = SourceId::for_registry(&loc).unwrap();

        assert!(PackageId::try_new("foo", "1.0", repo).is_err());
        assert!(PackageId::try_new("foo", "1", repo).is_err());
        assert!(PackageId::try_new("foo", "bar", repo).is_err());
        assert!(PackageId::try_new("foo", "", repo).is_err());
    }

    #[test]
    fn display() {
        let loc = CRATES_IO_INDEX.into_url().unwrap();
        let pkg_id =
            PackageId::try_new("foo", "1.0.0", SourceId::for_registry(&loc).unwrap()).unwrap();
        assert_eq!("foo v1.0.0", pkg_id.to_string());
    }

    #[test]
    fn unequal_build_metadata() {
        let loc = CRATES_IO_INDEX.into_url().unwrap();
        let repo = SourceId::for_registry(&loc).unwrap();
        let first = PackageId::try_new("foo", "0.0.1+first", repo).unwrap();
        let second = PackageId::try_new("foo", "0.0.1+second", repo).unwrap();
        assert_ne!(first, second);
        assert_ne!(first.inner, second.inner);
    }

    fn package(name: &str, version: &str, source: SourceId) -> PackageId {
        PackageId::try_new(name, version, source).unwrap()
    }

    fn registry(url: &str) -> SourceId {
        SourceId::for_registry(&url.into_url().unwrap()).unwrap()
    }

    fn git(reference: GitReference) -> SourceId {
        let url = "https://example.invalid/package-id-order"
            .into_url()
            .unwrap();
        SourceId::for_git(&url, reference).unwrap()
    }

    fn assert_order(left: PackageId, right: PackageId, expected: Ordering) {
        assert_eq!(left.cmp(&right), expected, "{left:?} versus {right:?}");
        assert_eq!(right.cmp(&left), expected.reverse());
        assert_eq!(left.partial_cmp(&right), Some(expected));
        assert_eq!(right.partial_cmp(&left), Some(expected.reverse()));
        assert_eq!(left == right, expected == Ordering::Equal);
        assert_eq!(left < right, expected == Ordering::Less);
        assert_eq!(left <= right, expected != Ordering::Greater);
        assert_eq!(left > right, expected == Ordering::Greater);
        assert_eq!(left >= right, expected != Ordering::Less);
    }

    #[test]
    fn ordering_same_interned_identity() {
        let source = registry("https://example.invalid/index");
        let first = package("foo", "1.0.0+metadata", source);
        let second = package("foo", "1.0.0+metadata", source);
        assert!(ptr::eq(first.inner, second.inner));
        assert_order(first, second, Ordering::Equal);
    }

    #[test]
    fn ordering_ignores_precise_source_identity() {
        let git_source = git(GitReference::DefaultBranch);
        let registry_source = registry("https://example.invalid/index");
        let source_groups = [
            vec![
                git_source,
                git_source
                    .with_git_precise(Some("1111111111111111111111111111111111111111".into())),
                git_source
                    .with_git_precise(Some("2222222222222222222222222222222222222222".into())),
            ],
            vec![
                registry_source,
                registry_source.with_locked_precise(),
                registry_source
                    .with_precise_registry_version("foo".into(), "1.0.0".parse().unwrap(), "1.0.1")
                    .unwrap(),
                registry_source
                    .with_precise_registry_version("foo".into(), "1.0.0".parse().unwrap(), "1.0.2")
                    .unwrap(),
            ],
        ];
        for sources in source_groups {
            let packages: Vec<_> = sources
                .into_iter()
                .map(|source| package("foo", "1.0.0", source))
                .collect();
            for (i, &left) in packages.iter().enumerate() {
                for (j, &right) in packages.iter().enumerate() {
                    if i != j {
                        assert!(!left.source_id().full_eq(right.source_id()));
                        assert!(!ptr::eq(left.inner, right.inner));
                        assert_ne!(left.inner, right.inner);
                    }
                    assert_order(left, right, Ordering::Equal);
                    let mut left_hash = DefaultHasher::new();
                    let mut right_hash = DefaultHasher::new();
                    left.hash(&mut left_hash);
                    right.hash(&mut right_hash);
                    assert_eq!(left_hash.finish(), right_hash.finish());
                }
            }
            assert_eq!(packages.into_iter().collect::<BTreeSet<_>>().len(), 1);
        }
    }

    #[test]
    fn ordering_uses_complete_semver() {
        let source = registry("https://example.invalid/index");
        let versions = [
            "0.0.1-alpha.2",
            "0.0.1-alpha.10",
            "0.0.1",
            "0.0.1+1",
            "0.0.1+01",
            "0.0.1+2",
            "0.0.1+first",
            "0.0.1+second",
            "0.0.2",
            "0.1.0",
            "1.0.0",
        ];
        for (i, left) in versions.iter().enumerate() {
            for (j, right) in versions.iter().enumerate() {
                assert_order(
                    package("foo", left, source),
                    package("foo", right, source),
                    i.cmp(&j),
                );
            }
        }
    }

    #[test]
    fn ordering_respects_field_priority() {
        let low = registry("https://a.example.invalid/index");
        let high = registry("https://z.example.invalid/index");
        assert_order(
            package("alpha", "9.0.0", high),
            package("zeta", "0.0.1", low),
            Ordering::Less,
        );
        assert_order(
            package("foo", "1.0.0", high),
            package("foo", "2.0.0", low),
            Ordering::Less,
        );
        assert_order(
            package("foo", "1.0.0", low),
            package("foo", "1.0.0", high),
            Ordering::Less,
        );
    }

    #[test]
    fn ordering_preserves_source_semantics() {
        let sources = [
            registry("https://z.example.invalid/index"),
            registry("sparse+https://a.example.invalid/index/"),
            git(GitReference::Tag("v1.0.0".into())),
            git(GitReference::Branch("main".into())),
            git(GitReference::Rev(
                "1111111111111111111111111111111111111111".into(),
            )),
            git(GitReference::DefaultBranch),
        ];
        for (i, &left) in sources.iter().enumerate() {
            for (j, &right) in sources.iter().enumerate() {
                assert_order(
                    package("foo", "1.0.0", left),
                    package("foo", "1.0.0", right),
                    i.cmp(&j),
                );
            }
        }

        let https = "https://github.com/package-id-order/repository"
            .into_url()
            .unwrap();
        let git_url = "git://github.com/package-id-order/repository"
            .into_url()
            .unwrap();
        assert_order(
            package(
                "foo",
                "1.0.0",
                SourceId::for_git(&https, GitReference::DefaultBranch).unwrap(),
            ),
            package(
                "foo",
                "1.0.0",
                SourceId::for_git(&git_url, GitReference::DefaultBranch).unwrap(),
            ),
            Ordering::Equal,
        );

        let url = "https://example.invalid/display-alias".into_url().unwrap();
        let first = SourceId::for_alt_registry(&url, "first-name").unwrap();
        let second = SourceId::for_alt_registry(&url, "second-name").unwrap();
        assert_order(
            package("foo", "1.0.0", first),
            package("foo", "1.0.0", second),
            Ordering::Equal,
        );
    }

    #[test]
    fn ordering_matches_derived_inner() {
        let low = registry("https://a.example.invalid/index");
        let high = registry("https://z.example.invalid/index");
        let git_source = git(GitReference::DefaultBranch);
        let groups = [
            vec![package("alpha", "9.0.0", git_source)],
            vec![package("foo", "1.0.0-alpha.2", git_source)],
            vec![
                package("foo", "1.0.0", low),
                package("foo", "1.0.0", low.with_locked_precise()),
            ],
            vec![package("foo", "1.0.0", high)],
            vec![
                package("foo", "1.0.0", git_source),
                package(
                    "foo",
                    "1.0.0",
                    git_source
                        .with_git_precise(Some("1111111111111111111111111111111111111111".into())),
                ),
            ],
            vec![package("foo", "1.0.0+1", low)],
            vec![package("zeta", "0.0.1", low)],
        ];
        for (i, left_group) in groups.iter().enumerate() {
            for (j, right_group) in groups.iter().enumerate() {
                for &left in left_group {
                    for &right in right_group {
                        assert_order(left, right, i.cmp(&j));
                        assert_eq!(left.cmp(&right), left.inner.cmp(right.inner));
                        assert_eq!(
                            left.partial_cmp(&right),
                            left.inner.partial_cmp(right.inner)
                        );
                    }
                }
            }
        }
        let packages: Vec<_> = groups.iter().flatten().copied().collect();
        for &first in &packages {
            for &second in &packages {
                for &third in &packages {
                    if first <= second && second <= third {
                        assert!(first <= third);
                    }
                }
            }
        }
        let mut sorted: Vec<_> = packages.iter().rev().copied().collect();
        sorted.sort();
        assert_eq!(sorted, packages);
        let ordered: BTreeSet<_> = packages.into_iter().collect();
        let expected: Vec<_> = groups.iter().map(|group| group[0]).collect();
        assert_eq!(ordered.into_iter().collect::<Vec<_>>(), expected);
    }
}
