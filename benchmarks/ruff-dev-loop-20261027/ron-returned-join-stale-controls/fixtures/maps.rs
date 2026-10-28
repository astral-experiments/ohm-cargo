#![feature(proc_macro_tracked_path)]
extern crate proc_macro;
use std::{env,fs,os::unix::fs::MetadataExt};
use proc_macro::{Literal,TokenStream,TokenTree};
#[used]
static ANCHOR: u8 = 17;
#[proc_macro]
pub fn image_topology(_: TokenStream)->TokenStream {
    let address = std::ptr::addr_of!(ANCHOR) as usize;
    let input=std::path::PathBuf::from(env::var_os("OHM_JOIN_ORIGINAL").unwrap());
    let alias=std::path::PathBuf::from(env::var_os("OHM_JOIN_ALIAS").unwrap());
    proc_macro::tracked::path(&input);
    proc_macro::tracked::path(&alias);
    let rows=fs::read_to_string("/proc/self/maps").unwrap();
    let line=rows.lines().find(|line| {
        let r=line.split_whitespace().next().unwrap();
        let (a,b)=r.split_once('-').unwrap();
        (usize::from_str_radix(a,16).unwrap()..usize::from_str_radix(b,16).unwrap()).contains(&address)
    }).unwrap();
    let words:Vec<_>=line.split_whitespace().collect();
    let m=fs::metadata(&input).unwrap();let a=fs::metadata(&alias).unwrap();
    let same_alias=m.dev()==a.dev() && m.ino()==a.ino();
    let loaded_same_alias=words[4].parse::<u64>().unwrap()==a.ino();
    let mapped_name_is_input=words[5]==input.to_str().unwrap();
    let result=format!("alias={same_alias};mapped_alias={loaded_same_alias};mapped_name={mapped_name_is_input};nlink={}",m.nlink());
    TokenTree::Literal(Literal::string(&result)).into()
}
