pub fn from_workspace(value: &ruff_workspace::Settings) -> &ruff_linter::settings::LinterSettings {
    &value.linter
}

pub fn load_graph_signature() {
    let _ = ruff_graph::ModuleImports::detect;
}
