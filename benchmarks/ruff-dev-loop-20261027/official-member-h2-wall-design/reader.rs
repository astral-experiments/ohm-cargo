fn main() {
    #[cfg(member_wasm)]
    assert_eq!(ty_wasm::version(), "93526150d");
    #[cfg(member_project)]
    assert!(std::mem::size_of::<ty_project::ProjectMetadata>() > 0);
    let stub = ty_vendored::file_system().read_to_string("stdlib/functools.pyi").unwrap();
    print!("{stub}");
}
