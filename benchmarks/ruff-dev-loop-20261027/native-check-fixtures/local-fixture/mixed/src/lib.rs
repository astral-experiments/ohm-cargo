pub struct Token(pub u32); pub fn token()->Token { Token(7) }
#[unsafe(no_mangle)] pub extern "C" fn exported()->u32 { token().0 }
