pub fn observe(c: &ty_ide::Completion<'_>) { if let Some(d) = &c.documentation { let _ = d.render(ty_ide::MarkupKind::PlainText); } }
