#[link(name = "ohm_env_choice", kind = "static", modifiers = "-bundle")]
unsafe extern "C" { fn ohm_env_choice_value() -> i32; }
#[test]
fn reads_the_linked_archive() {
    println!("native-value={}", unsafe { ohm_env_choice_value() });
}
