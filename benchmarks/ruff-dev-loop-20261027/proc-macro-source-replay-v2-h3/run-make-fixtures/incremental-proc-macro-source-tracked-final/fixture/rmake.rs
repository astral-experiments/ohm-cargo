//@ ignore-cross-compile
//@ needs-crate-type: proc-macro
//@ ignore-musl (FIXME: can't find `-lunwind`)

use std::path::Path;

use run_make_support::{Rustc, dynamic_lib_name, rfs, run, rustc};

fn producer(cache: &str) -> Rustc {
    let mut cmd = rustc();
    cmd.input("producer.rs")
        .edition("2024")
        .extern_("maker", dynamic_lib_name("maker"))
        .incremental(cache)
        .arg("-Zcache-proc-macros")
        .arg("-Zpublic-api-hash")
        .emit("link,metadata");
    cmd
}

fn save_bridge(history: &str) {
    rustc().input("bridge.rs").extern_("producer", "libproducer.rlib").run();
    rfs::create_dir(history);
    for name in ["libproducer.rlib", "libproducer.rmeta", "libbridge.rlib"] {
        rfs::copy(name, Path::new(history).join(name));
    }
}

fn caller(producer: &str, bridge: &str) -> String {
    for name in ["libproducer.rlib", "libproducer.rmeta"] {
        rfs::copy(Path::new(producer).join(name), name);
    }
    rfs::copy(Path::new(bridge).join("libbridge.rlib"), "libbridge.rlib");
    rustc().input("caller.rs").extern_("bridge", "libbridge.rlib").run();
    run("caller").stdout_utf8()
}

fn main() {
    rustc().input("maker.rs").run();
    rfs::write("parse-input.txt", "91");
    producer("incremental").run().assert_stderr_contains("executed derive");
    let original = rfs::read_to_string("producer.rs");
    rfs::write("producer.rs", original.replace("    7", "    8"));
    rfs::write("parse-input.txt", "379");

    producer("incremental")
        .run()
        .assert_stderr_not_contains("executed attribute")
        .assert_stderr_not_contains("executed derive")
        .assert_stderr_contains("executed tracked derive");
    save_bridge("warm");
    producer("empty")
        .run()
        .assert_stderr_contains("executed attribute")
        .assert_stderr_contains("executed derive");
    save_bridge("clean");

    // A later macro embeds the included file's absolute span in the native program.
    let clean = caller("clean", "clean");
    assert_eq!(caller("warm", "warm"), clean);
    // Each ordinary bridge must also accept the independently rebuilt producer.
    assert_eq!(caller("warm", "clean"), clean);
    assert_eq!(caller("clean", "warm"), clean);
    assert!(rfs::read("warm/libproducer.rmeta") == rfs::read("clean/libproducer.rmeta"));
}
