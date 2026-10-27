"""Compile a normal Rust bridge and a fresh consumer against both mixed-library outputs."""
import argparse
from pathlib import Path
import subprocess
import tempfile


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("crate", choices=["ruff_wasm", "ty_wasm"])
    p.add_argument("--sysroot", type=Path, required=True)
    for arm in ["replay", "full"]:
        p.add_argument(f"--{arm}-rlib", type=Path, required=True)
        p.add_argument(f"--{arm}-search", type=Path, required=True,
                       help="File with one -L value per line from this arm's actual rustc invocation")
    p.add_argument("--rustc", default="rustc")
    p.add_argument("--toolchain", default="ohm")
    p.add_argument("--wild-dir", type=Path, help="Directory containing the bundled ld.bfd")
    args = p.parse_args()
    rustc = [args.rustc, "+" + args.toolchain, "--sysroot", str(args.sysroot), "--edition=2024"]
    if args.wild_dir:
        rustc += ["-C", "link-arg=-B" + str(args.wild_dir)]
    api = "Workspace::version()" if args.crate == "ruff_wasm" else "version()"
    with tempfile.TemporaryDirectory() as run:
        out = Path(run)
        bridge = out / "bridge.rs"
        bridge.write_text(f"pub fn observed() -> String {{ {args.crate}::{api}.to_string() }}\n")
        caller = out / "main.rs"
        caller.write_text('fn main() { println!("{}", ordinary_bridge::observed()); }\n')
        rosters = {}
        bridges = {}
        for arm in ["replay", "full"]:
            rlib = getattr(args, arm + "_rlib").resolve(strict=True)
            paths = getattr(args, arm + "_search").read_text().splitlines()
            search = ["-L", "dependency=" + str(rlib.parent)]
            for value in paths:
                if value:
                    search += ["-L", value]
            rosters[arm] = search
            lib = out / arm / "libordinary_bridge.rlib"
            lib.parent.mkdir()
            subprocess.run([*rustc, "--crate-name", "ordinary_bridge", "--crate-type", "rlib",
                            bridge, "--extern", args.crate + "=" + str(rlib), *search, "-o", lib],
                           check=True)
            bridges[arm] = lib
        for issuer, lib in bridges.items():
            for consumer, paths in rosters.items():
                exe = out / (issuer + "-" + consumer)
                p = subprocess.run([*rustc, "--crate-name", "ordinary_user", caller, "--extern",
                                    "ordinary_bridge=" + str(lib), *paths, "-o", exe],
                                   capture_output=True, text=True)
                if issuer == consumer:
                    assert p.returncode == 0, p.stderr
                    print(issuer, consumer, subprocess.check_output([exe], text=True).strip())
                else:
                    assert p.returncode != 0 and "E0460" in p.stderr and args.crate in p.stderr, p.stderr
                    print(issuer, consumer, "E0460")


if __name__ == "__main__":
    main()
