extern crate proc_macro;
use proc_macro::{TokenStream, TokenTree};
use std::{env, fs, thread, time::{Duration, Instant}};
use std::hash::{DefaultHasher, Hasher};
use std::path::PathBuf;

#[proc_macro]
pub fn wait_value(input: TokenStream) -> TokenStream {
    if let Some(dir) = env::var_os("LOCK_QA_BARRIER") {
        let dir = PathBuf::from(dir);
        let checkout = PathBuf::from(env::var_os("CARGO_MANIFEST_DIR").unwrap());
        let head = fs::read(checkout.join(".git/HEAD")).unwrap();
        let mut hasher = DefaultHasher::new();
        hasher.write(head.trim_ascii_end());
        let tmp = dir.join("ready.tmp");
        fs::write(&tmp, format!("{} {:016x}\n", std::process::id(), hasher.finish())).unwrap();
        fs::rename(tmp, dir.join("ready")).unwrap();
        let start = Instant::now();
        while !dir.join("release").exists() {
            assert!(start.elapsed() < Duration::from_secs(100), "private barrier timed out");
            thread::sleep(Duration::from_millis(20));
        }
    }
    let value = input.into_iter().next().unwrap();
    assert!(matches!(&value, TokenTree::Literal(_)));
    TokenStream::from(value)
}
