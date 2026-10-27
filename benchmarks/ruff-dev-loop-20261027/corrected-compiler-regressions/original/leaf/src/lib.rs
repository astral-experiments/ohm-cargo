#![allow(dead_code)]
#[cfg(any())] mod p0;
pub mod defs;
pub fn indirect(x:i32)->i32 { 42/x }
struct Local;
impl Iterator for Local {
    type Item = u8;
    fn next(&mut self)->Option<Self::Item> { None }
}
