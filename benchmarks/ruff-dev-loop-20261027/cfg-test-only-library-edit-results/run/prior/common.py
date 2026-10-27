"""Fixed Ruff workspace, native artifact, CLI and execve witnesses for the H2 protocol."""

import ast
import hashlib
import json
import mmap
import os
from pathlib import Path
import re
import struct
import subprocess

P = Path("/mnt/devbox-scratch/dev-user/ohm-whole-skips-20261027")
RUFF = Path("/home/dev-user/code/oss/ruff-ohm-whole-native-20261027")
FROZEN = P / "frozen-toolchain"
SONAME = "librustc_driver-774a793a844d5500.so"
TARGET = P / "native-target"
SHARED = P / "shared"
CARGO_HOME = P / "registry-home"
PLAN = Path(__file__).with_name("plan.json")
PIN = "93526150df078af7dd8fc4226cdcc469539d2001"
MODE_COUNTS = {"build": (501, 15), "test": (619, 110)}
MATCH_FILE = RUFF / "crates/ruff_linter/src/rules/ruff/helpers.rs"
NEEDLE = b'qualified_name.segments(), ["dataclasses", "field"]'
REPLACEMENT = b'qualified_name.segments(), ["dataclasses", "other"]'
DATACLASS = b"from dataclasses import dataclass, field\n@dataclass\nclass C:\n    a: list[int] = field(default=[])\n    b: list[int] = field(default_factory=list)\n    c: list[int] = []\n"


def need(condition, message):
    if not condition:
        raise ValueError(message)


def sha(path):
    with Path(path).open("rb") as src:
        return hashlib.file_digest(src, "sha256").hexdigest()


def dump(path, data):
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")


def load(path):
    return json.loads(path.read_bytes())


def git(*args):
    return subprocess.check_output(["git", "--no-optional-locks", "-C", RUFF, *args], text=True).strip()


def env():
    return dict(
        os.environ,
        RUSTUP_HOME=str(P / "rustup"),
        RUSTUP_AUTO_INSTALL="0",
        CARGO_HOME=str(CARGO_HOME),
        CARGO_TARGET_DIR=str(TARGET),
        CARGO_BUILD_BUILD_DIR=str(SHARED),
        CARGO_BUILD_JOBS="8",
        CARGO_UNSTABLE_OHM_PROC_MACRO_TRUST="all",
        CARGO_UNSTABLE_OHM_NATIVE_TOOL_TRUST="all",
        GIT_OPTIONAL_LOCKS="0",
        LC_ALL="C.UTF-8",
        CARGO_TERM_COLOR="never",
        SSL_CERT_FILE="/etc/ssl/certs/ca-certificates.crt",
        SSL_CERT_DIR="/etc/ssl/certs",
    )


def diagnostics(ruff, edited):
    result = {}
    for key, options, data in [
        ("mixed", ["--target-version", "py314"], b"t'first' b'second'\n"),
        ("dataclass", ["--preview", "--select", "RUF008", "--stdin-filename", "case.py"], DATACLASS),
    ]:
        q = subprocess.run(
            [str(ruff), "check", "--isolated", "--no-cache", "--output-format", "json", *options, "-"],
            input=data,
            capture_output=True,
            env=env(),
            cwd=RUFF,
        )
        need(q.returncode == 1 and not q.stderr, (key, q.returncode, q.stderr))
        result[key] = json.loads(q.stdout)
    need(
        [d["message"] for d in result["mixed"]]
        == ["Cannot mix t-string literals with string or bytes literals"],
        result["mixed"],
    )
    positions = [(d["code"], d["location"]["row"], d["location"]["column"]) for d in result["dataclass"]]
    need(positions == ([("RUF008", 6, 20)] if edited else [("RUF008", 4, 34), ("RUF008", 6, 20)]), positions)
    return result


def elf(path):
    """Keep the exact file hash. Separately attest the two known Wild bytes classes, including all padding/header bytes outside them."""
    with path.open("rb") as f, mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ) as data:
        need(data[:6] == b"\x7fELF\x02\x01", path)
        (shoff,) = struct.unpack_from("<Q", data, 40)
        size, count, names_idx = struct.unpack_from("<HHH", data, 58)
        need(size == 64 and 0 < names_idx < count, path)
        headers = [struct.unpack_from("<IIQQQQIIQQ", data, shoff + i * size) for i in range(count)]
        strings = headers[names_idx]
        spans, witness, section_hashes = [], {}, {}
        for i, head in enumerate(headers):
            start = strings[4] + head[0]
            end = data.find(b"\0", start, strings[4] + strings[5])
            need(end >= start, path)
            name = data[start:end]
            section_hashes[name.decode('utf-8','backslashreplace')] = {
                'size': head[5], 'type': head[1], 'flags': head[2], 'entsize': head[9],
                'bytes': None if head[1] == 8 else hashlib.sha256(memoryview(data)[head[4]:head[4]+head[5]]).hexdigest(),
            }
            if name == b".note.gnu.build-id":
                offset, length = head[4:6]
                namesz, descsz, kind = struct.unpack_from("<III", data, offset)
                need(
                    head[1] == 7
                    and namesz == 4
                    and kind == 3
                    and length == 16 + (descsz + 3) // 4 * 4
                    and data[offset + 12 : offset + 16] == b"GNU\0",
                    path,
                )
                spans.append((offset + 16, descsz))
                witness["gnu_build_id"] = data[offset + 16 : offset + 16 + descsz].hex()
            if name == b".rodata":
                spans.append((shoff + i * size + 56, 8))
                witness["rodata_entsize"] = head[9]
        h = hashlib.sha256()
        at = 0
        for offset, length in sorted(spans):
            need(at <= offset <= len(data) - length, path)
            h.update(memoryview(data)[at:offset])
            h.update(b"\0" * length)
            at = offset + length
        h.update(memoryview(data)[at:])
        witness.update(
            raw=hashlib.sha256(data).hexdigest(),
            content_with_two_wild_fields_masked=h.hexdigest(),
            size=len(data),
            section_hashes=section_hashes,
        )
        return witness


def compare_elf(left, right):
    need(left.keys() == right.keys(), ["ELF roster", left.keys() ^ right.keys()])
    differences = {}
    for name, a in left.items():
        b = right[name]
        if a["raw"] != b["raw"]:
            need(
                a["size"] == b["size"]
                and a["content_with_two_wild_fields_masked"] == b["content_with_two_wild_fields_masked"],
                ["unexplained ELF difference", name, a, b],
            )
            differences[name] = [a, b]
    return differences


def trace(directory, require_cargo=True):
    execs = []
    work = []
    links = []
    other_rustc = []
    target_processes = []
    for file in sorted(directory.glob("exec.*")):
        pending = None
        for row in file.read_text(errors="replace").splitlines():
            if row.startswith(("execve(", "execveat(")) and row.endswith("<unfinished ...>"):
                need(pending is None, ("overlapping exec records", file))
                pending = row.removesuffix("<unfinished ...>")
                continue
            resumed = re.match(r"^<\.\.\. (execve(?:at)?) resumed>(.*)$", row)
            if resumed:
                need(
                    pending is not None and pending.startswith(resumed[1] + "("),
                    ("unmatched exec resume", file),
                )
                row, pending = pending + resumed[2], None
            if row.startswith("execveat(") and re.search(r"\)\s+= 0$", row):
                raise ValueError(("unexpected successful execveat", file, row[:300]))
            if not re.search(r"\)\s+= 0$", row) or not row.startswith("execve("):
                continue
            match = re.match(r'execve\(("(?:[^"\\]|\\.)*"),\s*(\[.*\]),\s*(?:0x[\da-f]+|NULL)', row)
            need(match is not None, ("unparsed successful execve", file, row[:300]))
            executable = ast.literal_eval(match[1])
            cmd = [ast.literal_eval(s) for s in re.findall(r'"(?:[^"\\]|\\.)*"', match[2])]
            name = Path(executable).name
            execs.append([file.name, executable])
            if name == "rustc":
                crate = cmd[cmd.index("--crate-name") + 1] if "--crate-name" in cmd else None
                if crate and crate not in {"___", "__"}:
                    kind = "link-only" if "-Zlink-only" in cmd or "link-only" in cmd else "full"
                    work.append([crate, kind])
                else:
                    other_rustc.append(cmd)
            if name in {"ld", "ld.bfd", "ld.gold", "ld.lld", "rust-lld", "wild", "ld.wild", "mold"}:
                links.append(executable)
            if executable.startswith(str(TARGET) + "/") or executable.startswith(str(SHARED) + "/"):
                target_processes.append(executable)
        need(pending is None, ("truncated exec record", file))
    if require_cargo:
        need(any(Path(p).name == "cargo" for _, p in execs), ("missing actual Cargo exec", directory))
    return dict(
        executions=execs,
        rustc=sorted(work),
        rustc_queries=other_rustc,
        linkers=sorted(links),
        target_execs=sorted(target_processes),
    )
