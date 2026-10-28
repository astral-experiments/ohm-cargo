#[allow(unused_imports)] use managed_api::{Native, sample, wait_value};
#[derive(Native)]
struct Foo;
fn main(){println!("{}/{}",Foo::VALUE,0);}
