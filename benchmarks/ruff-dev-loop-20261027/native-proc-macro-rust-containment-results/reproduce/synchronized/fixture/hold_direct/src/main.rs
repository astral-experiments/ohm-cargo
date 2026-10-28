use hold_shapes::Number;
const _:Option<Number>=None;
use race_extern::{Native,sample};
#[derive(Native)]
struct Foo;
fn main(){println!("sample={}\njoin={}",Foo::VALUE,hold_tokens::inspect_value!(sample));}
