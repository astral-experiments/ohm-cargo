pub struct Public { pub x:i32 }
#[inline(always)] pub fn gg<T>(_: T, x:i32) -> i32 { 21/x }
#[inline(always)] pub fn hh<T>(_: T, x:i32) -> i32 { crate::indirect(x) }
