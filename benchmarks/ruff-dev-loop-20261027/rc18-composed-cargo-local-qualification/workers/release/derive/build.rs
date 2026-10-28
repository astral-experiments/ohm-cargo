use std::{env,fs,path::PathBuf,process::Command};
fn main(){
 let dir=PathBuf::from(env::var_os("OUT_DIR").unwrap());
 let choice=env::var("MANAGED_OBJECT_SOURCE").unwrap();
 assert!(choice=="17" || choice=="29");
 fs::write(dir.join("native.c"),format!("unsigned selected_literal(void){{return {choice};}}")).unwrap();
 assert!(Command::new("cc").current_dir(&dir).args(["-fPIC","-c","native.c","-o","choice.o"]).status().unwrap().success());
 println!("cargo:rustc-link-arg={}",dir.join("choice.o").display());
 println!("cargo:rerun-if-env-changed=MANAGED_OBJECT_SOURCE");
}
