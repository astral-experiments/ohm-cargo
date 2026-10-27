"""Compare rebuilt Ruff outputs with independent cold references at identical absolute paths."""
import argparse
from contextlib import contextmanager
import fcntl
import hashlib
import json
import mmap
import os
from pathlib import Path
import shutil
import struct
import subprocess
import sys

ROOT = Path("/mnt/devbox-scratch/dev-user/ohm-whole-skips-20261027")
REPO = Path("/home/dev-user/code/oss/ruff-ohm-whole-native-20261027")
OUT = ROOT / "reference-parser-v3"
TARGET = ROOT / "native-target"
SHARED = ROOT / "shared"
FRONT = ROOT / "frozen-toolchain"
DRIVER = FRONT / "lib/librustc_driver-774a793a844d5500.so"
CARGO = FRONT / "bin/cargo"
CARGO_SHA = "13396fe1c6886f41155ac24f507210c7a5f655e5b3279a28f45bf3a5e6bcaf08"
SUBJECTS = {
    "parent": "051b9d3f5861f984faa0f8c1d2ab9b5c28e483a05c728051de837291c83fd518",
    "candidate": "55e123a9e87f16a449d260ab65449eab743cd30ba356a7f10ffdd1fa6f8a2484",
}
SOURCE_HASH = "08bb20f14fde4db57dd12ec3de3855021ddf6284b4a1957b54f4d06fb3c8f9ff"


def sha(path):
    with path.open("rb") as src:
        return hashlib.file_digest(src, "sha256").hexdigest()


def table_digest(values):
    digest = hashlib.sha256()
    for row in values:
        digest.update(struct.pack("<Q", len(row)))
        digest.update(row)
    return digest.hexdigest()


def elf_receipt(path):
    with path.open("rb") as f, mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ) as data:
        assert data[:6] == b"\x7fELF\x02\x01"
        shoff, = struct.unpack_from("<Q", data, 40)
        size, count, names_idx = struct.unpack_from("<HHH", data, 58)
        assert size == 64 and count and names_idx < count
        sections = [struct.unpack_from("<IIQQQQIIQQ", data, shoff + i * size) for i in range(count)]
        def string(section, offset):
            begin = section[4] + offset
            assert offset < section[5]
            end = data.find(b"\0", begin, section[4] + section[5])
            assert end >= begin
            return data[begin:end]
        names = [string(sections[names_idx], s[0]).decode() for s in sections]
        assert len(set(names)) == len(names)
        result = {}
        for name, s in zip(names, sections):
            _, kind, flags, addr, offset, length, link, info, alignment, entsize = s
            content = memoryview(data)[offset:offset + length] if kind != 8 else b""
            raw = hashlib.sha256(content).hexdigest()
            del content
            item = dict(type=kind, flags=flags, addr=addr, size=length, link=link, info=info,
                        alignment=alignment, entsize=entsize, digest=raw)
            if kind in (2, 11):
                assert entsize == 24 and length % entsize == 0
                symbols = []
                for pos in range(offset, offset + length, entsize):
                    name_pos, st_info, other, shndx, value, sym_size = struct.unpack_from("<IBBHQQ", data, pos)
                    symbol = string(sections[link], name_pos)
                    symbols.append(struct.pack("<BBHQQ", st_info, other, shndx, value, sym_size) + symbol)
                item.update(decoded_order=table_digest(symbols), decoded_set=table_digest(sorted(symbols)))
            result[name] = item
        return dict(raw_sha256=hashlib.sha256(data).hexdigest(), sections=result)


def write(path, obj):
    path.write_text(json.dumps(obj, indent=2, sort_keys=True) + "\n")


def run_inside(label, before):
    env = dict(os.environ, RUSTUP_HOME=str(ROOT / "rustup"), RUSTUP_AUTO_INSTALL="0",
               CARGO_HOME=str(ROOT / "registry-home"), CARGO_TARGET_DIR=str(TARGET),
               CARGO_BUILD_BUILD_DIR=str(SHARED), CARGO_BUILD_JOBS="8",
               CARGO_UNSTABLE_OHM_PROC_MACRO_TRUST="all", CARGO_UNSTABLE_OHM_NATIVE_TOOL_TRUST="all",
               CARGO_TERM_COLOR="never", LC_ALL="C.UTF-8", GIT_OPTIONAL_LOCKS="0",
               SSL_CERT_FILE="/etc/ssl/certs/ca-certificates.crt", SSL_CERT_DIR="/etc/ssl/certs")
    assert sha(DRIVER) == SUBJECTS[label.split("-")[0]] and not any(k.startswith("WILD_") for k in env)
    assert sha(CARGO) == CARGO_SHA
    for mode, count in (("build", 501), ("test", 619)):
        command = ["taskset", "-c", "0-23", "cargo", "+ohm", mode]
        if mode == "test":
            command.append("--no-run")
        command += ["--locked", "--offline", "--message-format=json"]
        receipt = {"command": command, "input": label, "mode": mode}
        stem = OUT / (label + "-" + mode + ("-original" if before else "-edited"))
        with stem.with_suffix(".stderr").open("wb") as stderr:
            run = subprocess.run(command, stdout=subprocess.PIPE, stderr=stderr, cwd=REPO, env=env, check=True)
        rows = [json.loads(line) for line in run.stdout.splitlines() if line.startswith(b"{")]
        units = [r for r in rows if r.get("reason") == "compiler-artifact"]
        assert len(units) == count and rows[-1]["success"]
        receipt["fresh"] = sum(r["fresh"] for r in units)
        receipt["dirty_local"] = sorted(r["target"]["name"] for r in units if not r["fresh"] and r["package_id"].startswith("path+"))
        receipt["diagnostics"] = [r["message"] for r in rows if r.get("reason") == "compiler-message"]
        if before:
            write(stem.with_suffix(".json"), receipt)
            continue
        products = {}
        executable_roster = set()
        binary = None
        for row in units:
            if not row["package_id"].startswith("path+"):
                continue
            if row["executable"]:
                executable_roster.add((row["package_id"], row["target"]["name"], tuple(row["target"]["kind"]),
                                       row["profile"]["test"], str(Path(row["executable"]).relative_to(TARGET))))
            if row["executable"] and row["target"]["name"] == "ruff" and row["target"]["kind"] == ["bin"] and not row["profile"]["test"]:
                binary = row["executable"]
            for p in map(Path, row["filenames"]):
                if p.suffix not in ("", ".so"):
                    continue
                with p.open("rb") as f:
                    if f.read(4) != b"\x7fELF":
                        continue
                key = "/".join(p.parts[-4:])
                if key not in products:
                    products[key] = elf_receipt(p)
        expected = (6, 15) if mode == "build" else (102, 110)
        assert binary and (len(executable_roster), len(products)) == expected, (mode, len(executable_roster), len(products))
        receipt["executables"] = sorted(executable_roster)
        receipt["products"] = products
        receipt["samples"] = []
        for sample in ("t'first' b'second'", "b'first' 'second'", "print('ok')", "import os"):
            oracle = [binary, "check", "--isolated", "--no-cache", "--target-version", "py314", "--output-format", "json", "-"]
            actual = subprocess.run(oracle, input=(sample + "\n").encode(), stdout=subprocess.PIPE, stderr=subprocess.PIPE, cwd=REPO, env=env)
            assert actual.returncode in (0, 1) and not actual.stderr
            diagnostics = json.loads(actual.stdout)
            if sample.startswith("t'"):
                assert "Bytes literal cannot be mixed with non-bytes literals" in [r["message"] for r in diagnostics]
            receipt["samples"].append([sample, actual.returncode, diagnostics])
        write(stem.with_suffix(".json"), receipt)


def orchestrate():
    with (ROOT / "native-measure.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        assert not subprocess.check_output(["git", "--no-optional-locks", "-C", REPO, "status", "--porcelain"])
        OUT.mkdir()
        patch = ROOT / "parser-assets/patches/parser-tstring.patch"
        assert sha(patch) == SOURCE_HASH
        names = subprocess.check_output(["git", "-C", REPO, "apply", "--numstat", patch]).decode().splitlines()
        files = [row.split("\t", 2)[2] for row in names]
        original = {name: sha(REPO / name) for name in files}
        assert all(n.startswith("crates/") and ".." not in Path(n).parts for n in files)
        saved = {n: ((REPO/n).read_bytes(), (REPO/n).stat()) for n in files}
        index = Path(subprocess.check_output(["git","-C",REPO,"rev-parse","--path-format=absolute","--git-path","index"],text=True).strip())
        index_sha = sha(index)
        edited = {}
        @contextmanager
        def apply_edit():
            subprocess.run(["git","-C",REPO,"apply","--reverse","--whitespace=nowarn",patch],check=True)
            try:
                states = {n: sha(REPO/n) if (REPO/n).exists() else None for n in files}
                if edited:
                    assert states == edited
                else:
                    edited.update(states)
                yield
            finally:
                for n,(data,st) in saved.items():
                    dest = REPO/n
                    dest.parent.mkdir(parents=True,exist_ok=True)
                    dest.write_bytes(data)
                    dest.chmod(st.st_mode & 0o777)
                    os.utime(dest,ns=(st.st_atime_ns,st.st_mtime_ns))
                assert sha(index) == index_sha
                assert not subprocess.check_output(["git","--no-optional-locks","-C",REPO,"status","--porcelain"])
        for arm in ("parent", "candidate"):
            fixed = FRONT / ".bench-components" / ("driver-" + SUBJECTS[arm])
            assert sha(fixed) == SUBJECTS[arm]
            for cache in ("warm", "cold"):
                label = arm + "-" + cache
                assert shutil.disk_usage(ROOT).free > 35 * 1024**3
                if cache == "warm":
                    src = "base" if arm == "parent" else "treatment"
                    target = ROOT / f"results-parser-{src}-test" / ("target-" + arm)
                    assert target.is_dir()
                    shared = SHARED
                else:
                    target, shared = OUT / (label + "-target"), OUT / (label + "-shared")
                    target.mkdir()
                    shared.mkdir()
                wrap = ["bwrap", "--ro-bind", "/", "/", "--proc", "/proc", "--dev-bind", "/dev", "/dev",
                        "--bind", "/tmp", "/tmp", "--bind", str(OUT), str(OUT),
                        "--bind", str(ROOT / "rustup"), str(ROOT / "rustup"),
                        "--bind", str(ROOT / "registry-home"), str(ROOT / "registry-home"),
                        "--bind", str(shared), str(SHARED), "--bind", str(target), str(TARGET),
                        "--ro-bind", str(ROOT / "subjects/parent"), str(CARGO), "--ro-bind", str(fixed), str(DRIVER)]
                inside = [sys.executable, str(Path(__file__).resolve()), "--inside", label]
                if cache == "warm":
                    subprocess.run(wrap + ["--"] + inside + ["--before"], check=True)
                with apply_edit():
                    subprocess.run(wrap + ["--"] + inside, check=True)
        assert original == {name: sha(REPO / name) for name in files}
        assert not subprocess.check_output(["git", "--no-optional-locks", "-C", REPO, "status", "--porcelain"])
        write(OUT / "complete.json", dict(source_clean=True, source=original, edited=edited, index_sha256=index_sha))


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--inside")
    cli.add_argument("--before", action="store_true")
    args = cli.parse_args()
    if args.inside:
        run_inside(args.inside, args.before)
    else:
        orchestrate()
