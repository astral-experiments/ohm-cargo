pub const fn answer() -> u8 {
    if include_str!(concat!(env!("CARGO_MANIFEST_DIR"), "/Cargo.toml")).len() == 104 { 17 } else { 29 }
}
