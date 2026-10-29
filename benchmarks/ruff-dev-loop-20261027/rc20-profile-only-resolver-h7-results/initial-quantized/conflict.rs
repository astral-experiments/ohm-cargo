#![allow(dead_code)]
extern crate self as get_size2;
pub trait GetSizeTracker {}
impl GetSizeTracker for () {}
pub fn default_tracker() {}
pub trait GetSize { fn get_heap_size(&self) -> usize; fn get_heap_size_with_tracker<T:GetSizeTracker>(&self,t:T)->(usize,T); }
fn measured(_: &u8) -> usize { 29 }
#[derive(get_size_derive2::GetSize)]
pub struct Value {
    #[get_size(size = 17, size_fn = measured, ignore)]
    pub field: u8,
}
