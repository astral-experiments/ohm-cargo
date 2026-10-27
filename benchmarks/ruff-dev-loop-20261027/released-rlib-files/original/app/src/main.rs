#[derive(Debug)] struct External;
fn main() {
    std::panic::set_hook(Box::new(|x| {let h=x.location().unwrap();println!("{}:{}:{}",h.file(),h.line(),h.column());}));
    let _=std::panic::catch_unwind(|| bundle::ratio(External,std::hint::black_box(0)));
    let _=std::panic::catch_unwind(|| bundle::nested(External,std::hint::black_box(0)));
    println!("{}",bundle::Public{x:7}.x);
}
