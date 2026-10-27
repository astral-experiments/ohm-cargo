//! A selected non-ELF input can be a linker script instead of a native library.
//! The normal linker dependency file identifies successful files. It does not identify
//! negative lookups made by relative script operands or by search directives.

/// Accept one system GROUP/INPUT whose only operands are absolute, observed paths.
pub(super) fn absolute_script(bytes: &[u8], observed: impl Fn(&str) -> bool) -> bool {
    let Ok(text) = std::str::from_utf8(bytes) else {
        return false;
    };
    let mut body = text.trim();
    if let Some(comment) = body.strip_prefix("/*") {
        let Some((_, remainder)) = comment.split_once("*/") else {
            return false;
        };
        body = remainder.trim();
    }
    let body = body.replace('(', " ( ").replace(')', " ) ");
    let mut tokens = body.split_ascii_whitespace();
    let mut command = tokens.next();
    if command == Some("OUTPUT_FORMAT") {
        if tokens.next() != Some("(")
            || tokens.next() != Some("elf64-x86-64")
            || tokens.next() != Some(")")
        {
            return false;
        }
        command = tokens.next();
    }
    if !matches!(command, Some("GROUP" | "INPUT")) || tokens.next() != Some("(") {
        return false;
    }
    let mut as_needed = false;
    let mut saw_input = false;
    while let Some(token) = tokens.next() {
        match token {
            "AS_NEEDED" if !as_needed && tokens.next() == Some("(") => {
                as_needed = true;
            }
            ")" if as_needed => as_needed = false,
            ")" => return saw_input && tokens.next().is_none(),
            path if path.starts_with('/')
                && path
                    .bytes()
                    .all(|b| b.is_ascii_alphanumeric() || b"/._+-".contains(&b))
                && observed(path) =>
            {
                saw_input = true;
            }
            _ => return false,
        }
    }
    false
}

#[cfg(test)]
mod tests {
    use super::absolute_script;

    #[test]
    fn scripts_only_contain_observed_absolute_operands() {
        let accepted =
            |s: &str| absolute_script(s.as_bytes(), |p| matches!(p, "/sys/liba" | "/sys/libb"));
        assert!(accepted(
            "/* GNU ld script */ OUTPUT_FORMAT(elf64-x86-64) GROUP ( /sys/liba AS_NEEDED (/sys/libb) )"
        ));
        assert!(accepted("INPUT(/sys/liba)"));
        for script in [
            "INPUT (x86_64-linux-gnu/librt.a)",
            "INPUT (extensionless)",
            "GROUP (libgcc_s.so.1 -lgcc)",
            "GROUP (/sys/liba AS_NEEDED (-lother))",
            "INPUT (/missing)",
            "INCLUDE /sys/liba",
            "SEARCH_DIR (/sys) INPUT (/sys/liba)",
            "INPUT (/sys/liba) marker = 151;",
            "INPUT (/sys/liba) {",
        ] {
            assert!(!accepted(script), "{script}");
        }
    }
}
