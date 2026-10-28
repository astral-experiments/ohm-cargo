pub struct Number;
pub fn count()->u32 {19}
/// One private shape
fn private_hint() {}
#[derive(Clone,Copy,Debug,PartialEq,Eq)] pub(super) enum Shape { Line, Circle }
#[derive(Clone,Copy,Debug,PartialEq,Eq)] pub(super) enum Tagged { Polygon(Shape), Empty }
