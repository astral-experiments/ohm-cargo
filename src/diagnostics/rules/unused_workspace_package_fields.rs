use std::path::Path;

use crate::util::data_structures::IndexSet;
use cargo_util_schemas::manifest::{InheritablePackage, TomlPackage};
use cargo_util_terminal::report::AnnotationKind;
use cargo_util_terminal::report::Group;
use cargo_util_terminal::report::Level;
use cargo_util_terminal::report::Origin;
use cargo_util_terminal::report::Snippet;
use tracing::instrument;

use super::SUSPICIOUS;
use crate::CargoResult;
use crate::GlobalContext;
use crate::diagnostics::Lint;
use crate::diagnostics::LintLevelProduct;
use crate::diagnostics::ScopedDiagnosticStats;
use crate::diagnostics::get_key_value_span;
use crate::diagnostics::workspace_rel_path;
use crate::workspace::MaybePackage;
use crate::workspace::Workspace;

pub static LINT: &Lint = &Lint {
    name: "unused_workspace_package_fields",
    primary_group: &SUSPICIOUS,
    msrv: Some(super::CARGO_LINTS_MSRV),
    feature_gate: None,
    docs: Some(
        r#"
### What it does
Checks for any fields in `[workspace.package]` that has not been inherited

### Why is this bad?
They can give the false impression that these fields are used

### Example
```toml
[workspace.package]
edition = "2024"

[package]
name = "foo"
```
"#,
    ),
};

#[instrument(skip_all)]
pub(crate) fn lint_workspace(
    ws: &Workspace<'_>,
    maybe_pkg: &MaybePackage,
    manifest_path: &Path,
    level: LintLevelProduct,
    pkg_stats: &mut ScopedDiagnosticStats<'_>,
    gctx: &GlobalContext,
) -> CargoResult<()> {
    let LintLevelProduct {
        level: lint_level,
        source,
    } = level;

    // Avoid materializing diagnostic spans in the common case where one member
    // inherits the entire table. Unknown keys, split inheritance and possible
    // warnings still use the documents below, preserving source order.
    if let Some(toml) = maybe_pkg.original_toml() {
        let Some(fields) = toml.workspace.as_ref().and_then(|w| w.package.as_ref()) else {
            return Ok(());
        };
        if toml._unused_keys.is_empty()
            && ws.members().any(|member| {
                let manifest = member.manifest();
                manifest
                    .original_toml()
                    .and_then(|t| t.package.as_deref())
                    .is_some_and(|pkg| inherits_all(fields, pkg))
                    && manifest.diagnostic_document().is_some()
            })
        {
            return Ok(());
        }
    }

    let workspace_package_fields: IndexSet<_> = maybe_pkg
        .document()
        .and_then(|d| d.get_ref().get("workspace"))
        .and_then(|w| w.get_ref().get("package"))
        .and_then(|p| p.get_ref().as_table())
        .iter()
        .flat_map(|d| d.keys())
        .collect();

    let mut inherited_fields = IndexSet::default();
    for member in ws.members() {
        if workspace_package_fields.is_subset(&inherited_fields) {
            return Ok(());
        }
        inherited_fields.extend(
            member
                .manifest()
                .document()
                .and_then(|w| w.get_ref().get("package"))
                .and_then(|p| p.get_ref().as_table())
                .iter()
                .flat_map(|d| {
                    d.iter()
                        .filter(|(_, v)| {
                            v.get_ref()
                                .get("workspace")
                                .and_then(|w| w.get_ref().as_bool())
                                == Some(true)
                        })
                        .map(|(k, _)| k)
                }),
        );
    }

    for (i, unused) in workspace_package_fields
        .difference(&inherited_fields)
        .enumerate()
    {
        let document = maybe_pkg.document();
        let contents = maybe_pkg.contents();
        let level = lint_level.to_diagnostic_level();
        let manifest_path = workspace_rel_path(ws, manifest_path);
        let emitted_source = LINT.emitted_source(lint_level, source);

        let mut primary = Group::with_title(
            level.primary_title(format!("unused field `{unused}` in `workspace.package`")),
        );
        if let Some(document) = document
            && let Some(contents) = contents
        {
            let mut snippet = Snippet::source(contents).path(&manifest_path);
            if let Some(span) =
                get_key_value_span(document, &["workspace", "package", unused.as_ref()])
            {
                snippet = snippet.annotation(AnnotationKind::Primary.span(span.key));
            }
            primary = primary.element(snippet);
        } else {
            primary = primary.element(Origin::path(&manifest_path));
        }
        if i == 0 {
            primary = primary.element(Level::NOTE.message(emitted_source));
        }
        let mut report = vec![primary];
        let help = Group::with_title(Level::HELP.secondary_title(format!(
            "consider removing the field `workspace.package.{unused}`"
        )));
        report.push(help);

        pkg_stats.record_lint(lint_level);
        gctx.shell().print_report(&report, lint_level.force())?;
    }

    Ok(())
}

fn inherits_all(fields: &InheritablePackage, package: &TomlPackage) -> bool {
    // Destructure exhaustively so new fields cannot silently bypass the lint.
    // Badges have no corresponding field in TomlPackage.
    macro_rules! check {
        ($($key:ident),+ $(,)?) => {{
            let InheritablePackage { badges, $($key,)+ } = fields;
            badges.is_none()
                $(&& ($key.is_none() || package.$key.as_ref().is_some_and(|v| v.is_inherited())))+
        }};
    }

    check!(
        version,
        authors,
        description,
        homepage,
        documentation,
        readme,
        keywords,
        categories,
        license,
        license_file,
        repository,
        publish,
        edition,
        exclude,
        include,
        rust_version,
    )
}
