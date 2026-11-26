use crate::util::CargoResult;
use crate::util::closest_msg;
use crate::util::data_structures::HashMap;
use crate::util::interning::InternedString;
use crate::workspace::{Dependency, PackageId, SourceId};
use anyhow::bail;
use cargo_util_schemas::manifest::FeatureName;
use cargo_util_schemas::manifest::RustVersion;
use semver::Version;
use std::collections::BTreeMap;
use std::fmt;
use std::hash::{Hash, Hasher};
use std::mem;
use std::sync::Arc;

/// Subset of a `Manifest`. Contains only the most important information about
/// a package.
///
/// Summaries are cloned, and should not be mutated after creation
#[derive(Debug, Clone)]
pub struct Summary {
    inner: Arc<Inner>,
}

#[derive(Debug, Clone)]
struct Inner {
    package_id: PackageId,
    dependencies: Vec<Dependency>,
    features: Arc<FeatureMap>,
    checksum: Option<String>,
    links: Option<InternedString>,
    rust_version: Option<RustVersion>,
    pubtime: Option<jiff::Timestamp>,
}

/// Indicates the dependency inferred from the `dep` syntax that should exist,
/// but missing on the resolved dependencies tables.
#[derive(Debug)]
pub struct MissingDependencyError {
    pub dep_name: InternedString,
    pub feature: InternedString,
    pub feature_value: FeatureValue,
    /// Indicates the dependency inferred from the `dep?` syntax that is weak optional
    pub weak_optional: bool,
}

impl std::error::Error for MissingDependencyError {}

impl fmt::Display for MissingDependencyError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        let Self {
            dep_name,
            feature,
            feature_value: fv,
            ..
        } = self;

        write!(
            f,
            "feature `{feature}` includes `{fv}`, but `{dep_name}` is not a dependency",
        )
    }
}

impl Summary {
    #[tracing::instrument(skip_all)]
    pub fn new(
        pkg_id: PackageId,
        dependencies: Vec<Dependency>,
        features: &BTreeMap<InternedString, Vec<InternedString>>,
        links: Option<impl Into<InternedString>>,
        rust_version: Option<RustVersion>,
    ) -> CargoResult<Summary> {
        // ****CAUTION**** If you change anything here that may raise a new
        // error, be sure to coordinate that change with either the index
        // schema field or the SummariesCache version.
        for dep in dependencies.iter() {
            let dep_name = dep.name_in_toml();
            if dep.is_optional() && !dep.is_transitive() {
                bail!(
                    "dev-dependencies are not allowed to be optional: `{}`",
                    dep_name
                )
            }
        }
        let feature_map = build_feature_map(features, &dependencies)?;
        Ok(Summary {
            inner: Arc::new(Inner {
                package_id: pkg_id,
                dependencies,
                features: Arc::new(feature_map),
                checksum: None,
                links: links.map(|l| l.into()),
                rust_version,
                pubtime: None,
            }),
        })
    }

    pub fn package_id(&self) -> PackageId {
        self.inner.package_id
    }
    pub fn name(&self) -> InternedString {
        self.package_id().name()
    }
    pub fn version(&self) -> &Version {
        self.package_id().version()
    }
    pub fn source_id(&self) -> SourceId {
        self.package_id().source_id()
    }
    pub fn dependencies(&self) -> &[Dependency] {
        &self.inner.dependencies
    }
    pub fn features(&self) -> &FeatureMap {
        &self.inner.features
    }

    pub(super) fn shared_features(&self) -> Arc<FeatureMap> {
        Arc::clone(&self.inner.features)
    }

    pub fn checksum(&self) -> Option<&str> {
        self.inner.checksum.as_deref()
    }
    pub fn links(&self) -> Option<InternedString> {
        self.inner.links
    }

    pub fn rust_version(&self) -> Option<&RustVersion> {
        self.inner.rust_version.as_ref()
    }

    pub fn pubtime(&self) -> Option<jiff::Timestamp> {
        self.inner.pubtime
    }

    pub fn override_id(mut self, id: PackageId) -> Summary {
        Arc::make_mut(&mut self.inner).package_id = id;
        self
    }

    pub fn set_checksum(&mut self, cksum: String) {
        Arc::make_mut(&mut self.inner).checksum = Some(cksum);
    }

    pub fn set_pubtime(&mut self, pubtime: jiff::Timestamp) {
        Arc::make_mut(&mut self.inner).pubtime = Some(pubtime);
    }

    pub fn map_dependencies<F>(self, mut f: F) -> Summary
    where
        F: FnMut(Dependency) -> Dependency,
    {
        self.try_map_dependencies(|dep| Ok(f(dep))).unwrap()
    }

    pub fn try_map_dependencies<F>(mut self, f: F) -> CargoResult<Summary>
    where
        F: FnMut(Dependency) -> CargoResult<Dependency>,
    {
        {
            let slot = &mut Arc::make_mut(&mut self.inner).dependencies;
            *slot = mem::take(slot)
                .into_iter()
                .map(f)
                .collect::<CargoResult<_>>()?;
        }
        Ok(self)
    }

    pub fn map_source(self, to_replace: SourceId, replace_with: SourceId) -> Summary {
        let me = if self.package_id().source_id() == to_replace {
            let new_id = self.package_id().with_source_id(replace_with);
            self.override_id(new_id)
        } else {
            self
        };
        me.map_dependencies(|dep| dep.map_source(to_replace, replace_with))
    }
}

impl PartialEq for Summary {
    fn eq(&self, other: &Summary) -> bool {
        self.inner.package_id == other.inner.package_id
    }
}

impl Eq for Summary {}

impl Hash for Summary {
    fn hash<H: Hasher>(&self, state: &mut H) {
        self.inner.package_id.hash(state);
    }
}

// A check that only compiles if Summary is Sync
const _: fn() = || {
    fn is_sync<T: Sync>() {}
    is_sync::<Summary>();
};

/// Checks features for errors, bailing out a CargoResult:Err if invalid,
/// and creates `FeatureValues` for each feature.
fn build_feature_map(
    features: &BTreeMap<InternedString, Vec<InternedString>>,
    dependencies: &[Dependency],
) -> CargoResult<FeatureMap> {
    use self::FeatureValue::*;
    if features.is_empty() && !dependencies.iter().any(Dependency::is_optional) {
        return Ok(FeatureMap::new());
    }

    // Keep feature usage with the dependency it describes. Several target
    // declarations may contribute to the same name.
    #[derive(Default)]
    struct DepInfo {
        optional: bool,
        explicit: bool,
        mentioned: bool,
    }
    let mut dep_map: HashMap<InternedString, DepInfo> = HashMap::default();
    for dep in dependencies {
        dep_map.entry(dep.name_in_toml()).or_default().optional |= dep.is_optional();
    }

    let mut map: FeatureMap = features
        .iter()
        .map(|(feature, list)| {
            let fvs: Vec<_> = list
                .iter()
                .map(|feat_value| {
                    let value = FeatureValue::new(*feat_value);
                    if let Dep { dep_name } = &value
                        && let Some(info) = dep_map.get_mut(dep_name)
                    {
                        info.explicit = true;
                    }
                    value
                })
                .collect();
            (*feature, fvs)
        })
        .collect();

    // Add implicit features for optional dependencies if they weren't
    // explicitly listed anywhere.
    for dep in dependencies {
        if !dep.is_optional() {
            continue;
        }
        let dep_name = dep.name_in_toml();
        if features.contains_key(&dep_name) || dep_map[&dep_name].explicit {
            continue;
        }
        map.insert(dep_name, vec![Dep { dep_name }]);
    }
    let map = map; // We are done mutating this variable

    // Validate features are listed properly.
    for (feature, fvs) in &map {
        FeatureName::new(feature)?;
        for fv in fvs {
            // Find data for the referenced dependency...
            let dep_data = dep_map.get_mut(&fv.feature_or_dep_name());
            let is_any_dep = dep_data.is_some();
            let is_optional_dep = dep_data.as_ref().is_some_and(|info| info.optional);
            if let Some(info) = dep_data {
                info.mentioned |= matches!(fv, Dep { .. } | DepFeature { .. });
            }
            match fv {
                Feature(f) => {
                    if !features.contains_key(f) {
                        if !is_any_dep {
                            let closest = closest_msg(f, features.keys(), |k| k, "feature");
                            bail!(
                                "feature `{feature}` includes `{fv}` which is neither a dependency \
                                 nor another feature{closest}"
                            );
                        }
                        if is_optional_dep {
                            if !map.contains_key(f) {
                                bail!(
                                    "feature `{feature}` includes `{fv}`, but `{f}` is an \
                                     optional dependency without an implicit feature\n\
                                     Use `dep:{f}` to enable the dependency."
                                );
                            }
                        } else {
                            bail!(
                                "feature `{feature}` includes `{fv}`, but `{f}` is not an optional dependency\n\
                                A non-optional dependency of the same name is defined; \
                                consider adding `optional = true` to its definition."
                            );
                        }
                    }
                }
                Dep { dep_name } => {
                    if !is_any_dep {
                        bail!(
                            "feature `{feature}` includes `{fv}`, but `{dep_name}` is not listed as a dependency"
                        );
                    }
                    if !is_optional_dep {
                        bail!(
                            "feature `{feature}` includes `{fv}`, but `{dep_name}` is not an optional dependency\n\
                             A non-optional dependency of the same name is defined; \
                             consider adding `optional = true` to its definition."
                        );
                    }
                }
                DepFeature {
                    dep_name,
                    dep_feature,
                    weak,
                } => {
                    // Early check for some unlikely syntax.
                    if dep_feature.contains('/') {
                        bail!(
                            "multiple slashes in feature `{fv}` (included by feature `{feature}`) are not allowed"
                        );
                    }

                    // dep: cannot be combined with /
                    if let Some(stripped_dep) = dep_name.strip_prefix("dep:") {
                        let creates_implicit = dep_map
                            .get(stripped_dep)
                            .is_some_and(|info| info.optional && !info.explicit);
                        let extra_help = if *weak || !creates_implicit {
                            // In this case, the user should just remove dep:.
                            // Note that "hiding" an optional dependency
                            // wouldn't work with just a single `dep:foo?/bar`
                            // because there would not be any way to enable
                            // `foo`.
                            String::new()
                        } else {
                            format!(
                                "\nIf the intent is to avoid creating an implicit feature \
                                 `{stripped_dep}` for an optional dependency, \
                                 then consider replacing this with two values:\n    \
                                 \"dep:{stripped_dep}\", \"{stripped_dep}/{dep_feature}\""
                            )
                        };
                        bail!(
                            "feature `{feature}` includes `{fv}` with both `dep:` and `/`\n\
                            To fix this, remove the `dep:` prefix.{extra_help}"
                        )
                    }

                    // Validation of the feature name will be performed in the resolver.
                    if !is_any_dep {
                        bail!(MissingDependencyError {
                            feature: *feature,
                            feature_value: (*fv).clone(),
                            dep_name: *dep_name,
                            weak_optional: *weak,
                        })
                    }
                    if *weak && !is_optional_dep {
                        bail!(
                            "feature `{feature}` includes `{fv}` with a `?`, but `{dep_name}` is not an optional dependency\n\
                            A non-optional dependency of the same name is defined; \
                            consider removing the `?` or changing the dependency to be optional"
                        );
                    }
                }
            }
        }
    }

    // Make sure every optional dep is mentioned at least once.
    if let Some((dep, _)) = dep_map
        .iter()
        .find(|(_, info)| info.optional && !info.mentioned)
    {
        bail!(
            "optional dependency `{dep}` is not included in any feature\n\
            Make sure that `dep:{dep}` is included in one of features in the [features] table."
        );
    }

    Ok(map)
}

/// `FeatureValue` represents the types of dependencies a feature can have.
#[derive(
    Clone, Debug, Ord, PartialOrd, Eq, PartialEq, Hash, serde::Serialize, serde::Deserialize,
)]
pub enum FeatureValue {
    /// A feature enabling another feature.
    Feature(InternedString),
    /// A feature enabling a dependency with `dep:dep_name` syntax.
    Dep { dep_name: InternedString },
    /// A feature enabling a feature on a dependency with `crate_name/feat_name` syntax.
    DepFeature {
        dep_name: InternedString,
        dep_feature: InternedString,
        /// If `true`, indicates the `?` syntax is used, which means this will
        /// not automatically enable the dependency unless the dependency is
        /// activated through some other means.
        weak: bool,
    },
}

impl FeatureValue {
    pub fn new(feature: InternedString) -> FeatureValue {
        match feature.split_once('/') {
            Some((dep, dep_feat)) => {
                let dep_name = dep.strip_suffix('?');
                FeatureValue::DepFeature {
                    dep_name: dep_name.unwrap_or(dep).into(),
                    dep_feature: dep_feat.into(),
                    weak: dep_name.is_some(),
                }
            }
            None => {
                if let Some(dep_name) = feature.strip_prefix("dep:") {
                    FeatureValue::Dep {
                        dep_name: dep_name.into(),
                    }
                } else {
                    FeatureValue::Feature(feature)
                }
            }
        }
    }

    fn feature_or_dep_name(&self) -> InternedString {
        match self {
            FeatureValue::Feature(dep_name)
            | FeatureValue::Dep { dep_name, .. }
            | FeatureValue::DepFeature { dep_name, .. } => *dep_name,
        }
    }
}

impl fmt::Display for FeatureValue {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        use self::FeatureValue::*;
        match self {
            Feature(feat) => write!(f, "{feat}"),
            Dep { dep_name } => write!(f, "dep:{dep_name}"),
            DepFeature {
                dep_name,
                dep_feature,
                weak,
            } => {
                let weak = if *weak { "?" } else { "" };
                write!(f, "{dep_name}{weak}/{dep_feature}")
            }
        }
    }
}

pub type FeatureMap = BTreeMap<InternedString, Vec<FeatureValue>>;

#[derive(Debug, serde::Serialize, serde::Deserialize)]
pub(crate) struct PackedIndexSummary {
    name: InternedString,
    version: semver::Version,
    dependencies: Vec<super::dependency::PackedIndexDependency>,
    features: FeatureMap,
    checksum: Option<String>,
    links: Option<InternedString>,
    rust_version: Option<RustVersion>,
    pubtime: Option<jiff::Timestamp>,
}

impl PackedIndexSummary {
    pub(crate) fn pack(summary: &Summary) -> Option<Self> {
        let s = &*summary.inner;
        Some(Self {
            name: s.package_id.name(),
            version: s.package_id.version().clone(),
            dependencies: s
                .dependencies
                .iter()
                .map(|d| {
                    super::dependency::PackedIndexDependency::pack(d, s.package_id.source_id())
                })
                .collect::<Option<_>>()?,
            features: (*s.features).clone(),
            checksum: s.checksum.clone(),
            links: s.links,
            rust_version: s.rust_version.clone(),
            pubtime: s.pubtime,
        })
    }
    pub(crate) fn unpack(self, source: SourceId) -> Option<Summary> {
        Some(Summary {
            inner: Arc::new(Inner {
                package_id: PackageId::new(self.name, self.version, source),
                dependencies: self
                    .dependencies
                    .into_iter()
                    .map(|d| d.unpack(source))
                    .collect::<Option<_>>()?,
                features: Arc::new(self.features),
                checksum: self.checksum,
                links: self.links,
                rust_version: self.rust_version,
                pubtime: self.pubtime,
            }),
        })
    }
}

#[cfg(test)]
mod feature_tests {
    use super::*;

    #[test]
    fn optional_feature_usage_across_declarations() {
        let source =
            SourceId::for_registry(&"https://example.invalid/index".parse().unwrap()).unwrap();
        let required = Dependency::parse("codec", Some("1"), source).unwrap();
        let mut optional = required.clone();
        optional.set_optional(true);
        let codec = InternedString::new("codec");

        let empty = BTreeMap::new();
        assert!(
            build_feature_map(&empty, std::slice::from_ref(&required))
                .unwrap()
                .is_empty()
        );
        let deps = [optional, required];
        assert_eq!(
            build_feature_map(&empty, &deps).unwrap()[&codec],
            [FeatureValue::Dep { dep_name: codec }]
        );

        let mut features = BTreeMap::from([("stream".into(), vec!["dep:codec".into()])]);
        assert!(
            !build_feature_map(&features, &deps)
                .unwrap()
                .contains_key(&codec)
        );

        // A feature with the dependency's name masks the implicit feature.
        // Referencing the feature alone does not use the dependency.
        features.insert(codec, vec![]);
        features.insert("stream".into(), vec![codec]);
        assert!(
            build_feature_map(&features, &deps)
                .unwrap_err()
                .to_string()
                .starts_with("optional dependency `codec` is not included")
        );

        features.insert("stream".into(), vec!["codec?/fast".into()]);
        assert!(build_feature_map(&features, &deps).is_ok());
    }
}
