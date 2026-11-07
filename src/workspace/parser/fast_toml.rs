//! Read Cargo schemas from an arena when the caller does not need TOML spans.
//! Unsupported values and errors go back to the diagnostic parser.

use cargo_util_schemas::{lockfile::TomlLockfile, manifest::TomlManifest};
use serde::Deserialize;
use serde::de::{self, IntoDeserializer, Visitor};
use toml_spanner::{Arena, Item, Value};

/// Preserve Cargo’s unused-key warnings for registry packages.
pub(super) fn manifest(source: &str) -> Option<TomlManifest> {
    with_document(source, |root| {
        super::deserialize_toml(Deserializer(root)).ok()
    })
}

pub(crate) fn lockfile(source: &str) -> Option<TomlLockfile> {
    with_document(source, |root| {
        TomlLockfile::deserialize(Deserializer(root)).ok()
    })
}

fn with_document<T>(source: &str, read: impl FnOnce(&Item<'_>) -> Option<T>) -> Option<T> {
    // The diagnostic parser limits inline array/table nesting to 80. Checking
    // every table here also sends deeply dotted tables back to that parser.
    fn supported(item: &Item<'_>, depth: u8) -> bool {
        match item.value() {
            Value::Array(items) => depth < 80 && items.into_iter().all(|v| supported(v, depth + 1)),
            Value::Table(table) => {
                depth < 80 && table.into_iter().all(|(_, v)| supported(v, depth + 1))
            }
            Value::Integer(value) => value.as_i64().is_some(),
            Value::Float(_) | Value::DateTime(_) => false,
            Value::Boolean(_) | Value::String(_) => true,
        }
    }
    let arena = Arena::new();
    let root = toml_spanner::parse(source, &arena).ok()?.into_item();
    if !supported(&root, 0) {
        return None;
    }
    read(&root)
}

struct Deserializer<'de, 'src>(&'de Item<'src>);

impl<'de, 'src> IntoDeserializer<'de, de::value::Error> for Deserializer<'de, 'src> {
    type Deserializer = Self;

    fn into_deserializer(self) -> Self {
        self
    }
}

impl<'de, 'src> serde::Deserializer<'de> for Deserializer<'de, 'src> {
    type Error = de::value::Error;

    fn deserialize_any<V: Visitor<'de>>(self, visitor: V) -> Result<V::Value, Self::Error> {
        match self.0.value() {
            Value::String(value) => visitor.visit_str(value),
            Value::Integer(value) => visitor.visit_i64(
                value
                    .as_i64()
                    .ok_or_else(|| de::Error::custom("integer outside i64"))?,
            ),
            Value::Boolean(value) => visitor.visit_bool(*value),
            Value::Array(values) => visitor.visit_seq(de::value::SeqDeserializer::new(
                values.into_iter().map(Deserializer),
            )),
            Value::Table(table) => visitor.visit_map(de::value::MapDeserializer::new(
                table.into_iter().map(|(k, v)| (k.name, Deserializer(v))),
            )),
            Value::Float(_) | Value::DateTime(_) => {
                Err(de::Error::custom("unsupported TOML value"))
            }
        }
    }

    fn deserialize_option<V: Visitor<'de>>(self, visitor: V) -> Result<V::Value, Self::Error> {
        visitor.visit_some(self)
    }

    fn deserialize_newtype_struct<V: Visitor<'de>>(
        self,
        _: &'static str,
        visitor: V,
    ) -> Result<V::Value, Self::Error> {
        visitor.visit_newtype_struct(self)
    }

    fn deserialize_enum<V: Visitor<'de>>(
        self,
        _: &'static str,
        _: &'static [&'static str],
        visitor: V,
    ) -> Result<V::Value, Self::Error> {
        match self.0.value() {
            Value::String(s) => visitor.visit_enum(s.into_deserializer()),
            _ => Err(de::Error::custom("use TOML's table enum deserializer")),
        }
    }

    fn deserialize_ignored_any<V: Visitor<'de>>(self, visitor: V) -> Result<V::Value, Self::Error> {
        visitor.visit_unit()
    }

    serde::forward_to_deserialize_any! {
        bool i8 i16 i32 i64 i128 u8 u16 u32 u64 u128 f32 f64 char str string
        bytes byte_buf unit unit_struct seq tuple tuple_struct map struct identifier
    }
}

#[cfg(test)]
mod tests {
    use super::{lockfile, manifest};
    use cargo_util_schemas::lockfile::TomlLockfile;

    #[test]
    fn registry_manifest_retains_unknown_keys() {
        let source = r#"
            [package]
            name = "example"
            version = "1.0.0"
            typo = true
            [package.metadata.release]
            channels = ["beta", "stable"]
            [dependencies.dep]
            version = "2"
            unknown = "unused"
        "#;
        let actual = manifest(source).unwrap();
        let expected =
            super::super::deserialize_toml(toml::de::Deserializer::parse(source).unwrap()).unwrap();
        assert!(actual._unused_keys.contains("package.typo"));
        assert_eq!(format!("{actual:?}"), format!("{expected:?}"));
    }

    #[test]
    fn lockfile_retains_legacy_metadata_and_unused_patches() {
        let source = r#"
            [root]
            name = "demo"
            version = "1.0.0"
            dependencies = ["dep 2.0.0"]
            [[package]]
            name = "dep"
            version = "2.0.0"
            source = "registry+https://github.com/rust-lang/crates.io-index"
            [[patch.unused]]
            name = "unused"
            version = "3.0.0"
            [metadata]
            "checksum dep 2.0.0" = "abcdef"
        "#;
        let actual = lockfile(source).unwrap();
        let expected = toml::from_str::<TomlLockfile>(source).unwrap();
        assert_eq!(
            serde_json::to_value(actual).unwrap(),
            serde_json::to_value(expected).unwrap()
        );
    }

    #[test]
    fn malformed_and_deep_documents_go_to_the_diagnostic_parser() {
        let deep = format!("ignored = {}0{}", "[".repeat(81), "]".repeat(81));
        for source in ["[broken", "key = 1\nkey = 2", deep.as_str()] {
            assert!(manifest(source).is_none());
            assert!(lockfile(source).is_none());
            assert!(toml::de::Deserializer::parse(source).is_err());
        }
        assert!(manifest("[package]\nname = 1").is_none());
        assert!(lockfile("version = \"4\"").is_none());
    }

    #[test]
    fn original_parser_handles_toml_metadata_values() {
        let source = "[package.metadata]\nratio = 1.25\ndate = 2026-11-07";
        assert!(manifest(source).is_none());
        assert!(
            super::super::deserialize_toml(toml::de::Deserializer::parse(source).unwrap()).is_ok()
        );
    }
}
