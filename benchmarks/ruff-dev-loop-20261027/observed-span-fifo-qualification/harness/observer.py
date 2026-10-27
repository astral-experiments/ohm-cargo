"""A private cross-file edit moves an observed stable proc_macro Span::Debug byte range."""

from pathlib import Path
import json
import os
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import dump, load, need, sha

BEFORE = """pub struct Public;
pub fn value() -> u32 { 7 }
#[macro_export] macro_rules! prime_file { ($callback:ident) => { $callback!(first_marker) }; }
/// private change
fn hidden() {}
#[derive(Debug, Copy, Clone, PartialEq, Eq)] pub(super) enum AttrsAutoAttribs { True, False, Inferred }
#[derive(Debug, Copy, Clone, PartialEq, Eq)] pub(super) enum DataclassKind { Standard, Attrs(AttrsAutoAttribs) }
"""
AFTER = BEFORE.replace("private change\n", "private changes\n")


def setup(ws):
    ws.mkdir()
    (ws / "Cargo.toml").write_text(
        '[workspace]\nresolver="2"\nmembers=["leaf","probe","app"]\n[profile.dev]\ndebug="line-tables-only"\nopt-level=1\n'
    )
    for name, manifest, unit, source in [
        (
            "leaf",
            "",
            "lib.rs",
            "#![allow(dead_code)]\nmod before; mod output; pub use before::{Public,value};\n",
        ),
        (
            "probe",
            "[lib]\nproc-macro=true\n",
            "lib.rs",
            """extern crate proc_macro;
use proc_macro::TokenStream;
#[proc_macro] pub fn read_span(input: TokenStream) -> TokenStream {
    let span = input.into_iter().next().unwrap().span();
    format!("{:?}",format!("{span:?}")).parse().unwrap()
}
#[proc_macro] pub fn swallow(_: TokenStream) -> TokenStream { "0u8".parse().unwrap() }
""",
        ),
        (
            "app",
            '[dependencies]\nleaf={path="../leaf"}\nprobe={path="../probe"}\n',
            "main.rs",
            'use probe::{swallow, read_span};\nconst _: u8=leaf::prime_file!(swallow);\nfn main(){println!("{} {}",leaf::value(),leaf::deliver!(read_span));}\n',
        ),
    ]:
        d = ws / name
        (d / "src").mkdir(parents=True)
        (d / "Cargo.toml").write_text(
            f'[package]\nname="{name}"\nversion="0.0.0"\nedition="2021"\n' + manifest
        )
        (d / "src" / unit).write_text(source)
    (ws / "leaf/src/before.rs").write_text(BEFORE)
    (ws / "leaf/src/output.rs").write_text(
        "#[macro_export]\nmacro_rules! deliver { ($callback:ident) => { $callback!(foreign_marker) }; }\n"
    )


def run(ws, out, environment, arm):
    out.mkdir()
    states = {}
    producer = ws / "leaf/src/before.rs"

    def step(name, target, content):
        if producer.read_text() != content:
            producer.write_text(content)
        where = out / name
        where.mkdir()
        cfg = dict(
            environment, CARGO_TARGET_DIR=str(target / "target"), CARGO_BUILD_BUILD_DIR=str(target / "build")
        )
        cmd = ["cargo", "+ohm", "build", "--offline", "--message-format=json", "-p", "app"]
        proc = subprocess.run(cmd, cwd=ws, env=cfg, capture_output=True)
        (where / "stdout").write_bytes(proc.stdout)
        (where / "stderr").write_bytes(proc.stderr)
        need(proc.returncode == 0, [name, proc.stderr[-1200:]])
        rows = [json.loads(l) for l in proc.stdout.splitlines()]
        arts = [x for x in rows if x["reason"] == "compiler-artifact"]
        need(len(arts) == 3 and rows[-1]["success"], name)
        (app,) = [x["executable"] for x in arts if x["executable"]]
        value = subprocess.check_output([app], cwd=ws, text=True).strip()
        need(value.startswith("7 #") and "bytes(" in value, (name, value))
        state = dict(
            value=value,
            dirty=sorted(a["target"]["name"] for a in arts if not a["fresh"]),
            source_sha=sha(producer),
            elf_sha=sha(app),
        )
        dump(where / "receipt.json", state)
        states[name] = state

    cached = out / "warm"
    cold = out / "cold"
    for name, store, src in [
        ("prime", cached, BEFORE),
        ("train", cached, BEFORE),
        ("before", cached, BEFORE),
        ("edit", cached, AFTER),
        ("repeat", cached, AFTER),
        ("independent-edit", cold, AFTER),
        ("restore", cached, BEFORE),
        ("restored-noop", cached, BEFORE),
    ]:
        step(name, store, src)
    value = lambda k: states[k]["value"]
    need(
        value("before") == value("prime") == value("restore") == value("restored-noop")
        and value("edit") == value("repeat") == value("independent-edit")
        and value("before") != value("edit"),
        states,
    )
    if arm == "candidate":
        need(all(not states[k]["dirty"] for k in ("before", "repeat", "restored-noop")), states)
    dump(out / "summary.json", states)


if __name__ == "__main__":
    from common import env

    ws, out = map(Path, sys.argv[1:3])
    run(ws, out, env(), sys.argv[3])
