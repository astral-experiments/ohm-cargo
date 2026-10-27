pub use ty_ide::Completion; pub fn has_docs(c: &Completion<'_>) -> bool { c.documentation.is_some() }
