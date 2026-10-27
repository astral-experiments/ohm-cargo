pub fn requires(p: pyproject_toml::PyProjectToml) -> Option<pep440_rs::VersionSpecifiers> { p.project?.requires_python }
