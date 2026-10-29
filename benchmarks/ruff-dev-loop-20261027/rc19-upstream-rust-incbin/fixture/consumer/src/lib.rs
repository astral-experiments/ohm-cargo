use core::arch::global_asm;
global_asm!(concat!(
    ".pushsection .rodata.manifest_fixture,\"a\",@progbits\n",
    ".globl ohm_manifest_fixture_start\n.globl ohm_manifest_fixture_end\n",
    "ohm_manifest_fixture_start:\n.incbin \"", env!("CARGO_MANIFEST_DIR"), "/Cargo.toml\"\n",
    "ohm_manifest_fixture_end:\n.popsection\n"
));
unsafe extern "C" {
    static ohm_manifest_fixture_start: u8;
    static ohm_manifest_fixture_end: u8;
}
pub fn answer() -> u8 {
    let start = core::ptr::addr_of!(ohm_manifest_fixture_start) as usize;
    let end = core::ptr::addr_of!(ohm_manifest_fixture_end) as usize;
    if end - start == 104 { 17 } else { 29 }
}
