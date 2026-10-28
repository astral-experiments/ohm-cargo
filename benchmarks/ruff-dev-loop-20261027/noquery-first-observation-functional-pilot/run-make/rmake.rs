//@ ignore-cross-compile

use std::path::Path;

use run_make_support::{dynamic_lib_name, rfs, run, rust_lib_name, rustc};

fn leaf_hash() -> String {
    rustc()
        .input("leaf.rs")
        .crate_type("rlib")
        .incremental("leaf-incr")
        .arg("-Zpublic-api-hash")
        .run();
    rustc().input(rust_lib_name("leaf")).arg("-Zls=public_hash").run().stdout_utf8()
}

fn client_with_flags(mode: &str, crate_type: &str, flags: &[&str]) -> String {
    rustc()
        .input("client.rs")
        .edition("2021")
        .crate_type(crate_type)
        .arg(format!("--cfg={mode}"))
        .extern_("probe", dynamic_lib_name("probe"))
        .extern_("leaf", rust_lib_name("leaf"))
        .emit("dep-info=actual.d,link")
        .arg("-Zpublic-api-hash")
        .args(flags)
        .run();
    rfs::read_to_string("actual.d")
}

fn client(mode: &str, crate_type: &str, expects_marker: bool) {
    let deps = client_with_flags(mode, crate_type, &[]);
    let marker = Path::new("actual.d").join("ohm-foreign-span-bytes");
    let inputs = deps.lines().find_map(|line| line.strip_prefix("actual.d: ")).unwrap();
    assert_eq!(inputs.split_whitespace().any(|p| Path::new(p) == marker), expects_marker, "{deps}");
    if mode == "text" {
        assert!(inputs.split_whitespace().any(|p| Path::new(p).ends_with("output.rs")), "{deps}");
    }
}

fn first_observation() {
    let first = ["-Zohm-observer-dep-info"];
    let forced = ["-Zbinary-dep-depinfo", "-Zchecksum-hash-algorithm=blake3"];
    let has_checksums = |deps: &str| deps.lines().any(|line| line.starts_with("# checksum:"));
    assert!(!has_checksums(&client_with_flags("clone_only", "rlib", &first)));
    let proof = client_with_flags("observer", "rlib", &first);
    assert!(has_checksums(&proof));
    assert_eq!(proof, client_with_flags("observer", "rlib", &forced));

    // With ordinary proc macro caching, old Make readers still get their original
    // rules. A cooperating Cargo can read the separately checksummed full input set.
    #[cfg(unix)]
    {
        let cached = ["-Zcache-proc-macros"];
        let prefix = "# ohm-observer-inputs-v1 ";
        let ordinary = client_with_flags("observer", "rlib", &[]);
        let on_demand = client_with_flags("observer", "rlib", &cached);
        let (header, rules) = on_demand.split_once('\n').unwrap();
        assert_eq!(rules, ordinary);
        let (digest, hex) = header.strip_prefix(prefix).unwrap().split_once(' ').unwrap();
        assert!(digest.starts_with("blake3="));
        let nested = (0..hex.len())
            .step_by(2)
            .map(|i| u8::from_str_radix(&hex[i..i + 2], 16).unwrap())
            .collect::<Vec<_>>();
        assert_eq!(nested, proof.as_bytes());
        assert!(!client_with_flags("clone_only", "rlib", &cached).contains(prefix));
    }

    // Do not certify normalized text as the original bytes. Explicit checksums on
    // the next compile can still authenticate both CRLF source and a binary include.
    let source = rfs::read_to_string("client.rs");
    rfs::write("payload.bin", [0xff, 0x07]);
    let edited = format!("{source}\nconst _: &[u8] = include_bytes!(\"payload.bin\");\n");
    rfs::write("client.rs", edited.replace('\n', "\r\n"));
    let pending = client_with_flags("observer", "rlib", &first);
    assert!(pending.contains("ohm-foreign-span-bytes") && !has_checksums(&pending));
    let trained = client_with_flags("observer", "rlib", &[forced[0], forced[1], first[0]]);
    assert!(has_checksums(&trained));
    assert_eq!(trained, client_with_flags("observer", "rlib", &forced));
    rfs::write("client.rs", source);
}

fn observed_byte_start() -> usize {
    client("observer", "bin", true);
    let output = run("client").stdout_utf8();
    let (_, bytes) = output.trim().split_once("bytes(").unwrap();
    bytes.split_once("..").unwrap().0.parse().unwrap()
}

fn main() {
    rustc().input("probe.rs").crate_type("proc-macro").run();
    let original = leaf_hash();
    first_observation();
    client("clone_only", "bin", false);
    client("local", "bin", false);
    let before = observed_byte_start();
    // Reading a foreign position in a downstream library must also guard its depinfo.
    client("observer", "rlib", true);

    // The first callback imports before.rs without inspecting its input. The next callback
    // sees the same token in output.rs, whose absolute byte position follows the first file.
    let source = rfs::read_to_string("before.rs");
    rfs::write("before.rs", source.replace("Private change", "Private changes"));
    assert_eq!(original, leaf_hash());
    assert_eq!(observed_byte_start(), before + 1);

    // source_text authenticates the complete original file, including comments after the macro.
    client("text", "bin", true);
    run("client").assert_stdout_equals("Some(\"foreign_marker\")\n");
    let output = rfs::read_to_string("output.rs");
    rfs::write("output.rs", output.replace("Unrelated note", "Unrelated edit"));
    assert_eq!(original, leaf_hash());
    client("text", "bin", true);
    run("client").assert_stdout_equals("Some(\"foreign_marker\")\n");

    // Ordinary dependency metadata already tracks the complete producer hash.
    rustc().input("leaf.rs").crate_type("rlib").run();
    client("observer", "rlib", false);
}
