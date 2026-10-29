pub fn invalid_workspace_field(value: &ruff_workspace::Settings) {
    let _ = &value.field_absent_from_ruff_settings;
}
