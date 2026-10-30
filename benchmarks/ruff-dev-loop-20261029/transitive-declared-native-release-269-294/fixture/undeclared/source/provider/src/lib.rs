#[link(name = "ohm_269_transitive", kind = "static", modifiers = "-bundle")]
extern "C" { fn native_value() -> i32; }
#[inline(never)]
pub fn value() -> i32 {
    let v = unsafe { native_value() };
    unsafe { core::arch::asm!("/* {0:e} */", in(reg) v, options(nomem, nostack, preserves_flags)); }
    v
}
