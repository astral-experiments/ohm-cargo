#![feature(proc_macro_tracked_path, proc_macro_tracked_env)]
extern crate proc_macro;
#[proc_macro]
pub fn native_offset(input:proc_macro::TokenStream)->proc_macro::TokenStream{
    let marker=input.into_iter().next().unwrap().span();
    format!("{:?}",format!("{marker:?}")).parse().unwrap()
}

#[proc_macro]
pub fn wait_value(input: proc_macro::TokenStream) -> proc_macro::TokenStream {
    assert_eq!(proc_macro::tracked::env_var("OHM_SYNC_CONSTANT").unwrap(), "fixed");
    let value = input.to_string();
    let root = std::path::PathBuf::from(std::env::var_os("OHM_SYNC_DIR").unwrap());
    let text = root.join("private-input.txt");
    let seen = if value == "file" {
        proc_macro::tracked::path(&text);
        std::fs::read_to_string(&text).unwrap()
    } else { value };
    if root.join("armed").is_file() {
        std::fs::write(root.join("observed"), &seen).unwrap();
        let start = std::time::Instant::now();
        while !root.join("release").is_file() {
            assert!(start.elapsed().as_secs() < 45);
            std::thread::sleep(std::time::Duration::from_millis(5));
        }
    }
    assert!(matches!(seen.trim(), "17" | "29"));
    seen.trim().parse().unwrap()
}
