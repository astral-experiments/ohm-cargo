#[macro_export]
macro_rules! same_file { () => { joined!(first last) } }
#[macro_export]
macro_rules! cross_file { ($left:ident) => { joined!($left last) } }
