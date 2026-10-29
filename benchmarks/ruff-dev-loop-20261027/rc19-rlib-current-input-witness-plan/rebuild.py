"""Rebuild one selected archive from current input FDs using an ordinary isolated LLVM archiver."""
import argparse
from collections import Counter
import filecmp
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess


def sha(path):
    with path.open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()


def archive_members(path):
    table = b""
    with path.open("rb") as src:
        assert src.read(8) == b"!<arch>\n"
        while (header := src.read(60)):
            assert len(header) == 60 and header[-2:] == b"\x60\n"
            name = header[:16].rstrip(b" ").decode()
            size = int(header[48:58])
            offset = src.tell()
            if re.fullmatch(r"/[0-9]+", name):
                start = int(name[1:])
                assert start == 0 or table[start - 2:start] == b"/\n"
                name = table[start:table.index(b"/\n", start)].decode()
            elif name not in ("/", "//"):
                name = name.removesuffix("/")
            data = src.read(size)
            assert len(data) == size
            if name == "//":
                table = data
            if size % 2:
                assert src.read(1) == b"\n"
            yield {"name": name, "offset": offset, "size": size, "sha256": hashlib.sha256(data).hexdigest()}


def link_or_copy(src, dst):
    try:
        os.link(src, dst)
    except OSError as error:
        import errno
        if error.errno != errno.EXDEV:
            raise
        shutil.copyfile(src, dst)


def isolated_writer(archiver, names, input_dir, output_dir, leaf):
    assert not list(output_dir.iterdir())
    mounts = ["bwrap", "--unshare-all", "--die-with-parent", "--ro-bind", "/usr", "/usr",
              "--symlink", "usr/lib", "/lib", "--symlink", "usr/lib64", "/lib64",
              "--dir", "/etc", "--ro-bind", "/etc/ld.so.cache", "/etc/ld.so.cache",
              "--dev", "/dev", "--proc", "/proc", "--tmpfs", "/tmp",
              "--ro-bind", str(input_dir), "/inputs", "--bind", str(output_dir), "/out",
              "--chdir", "/out", "--clearenv", "--setenv", "PATH", "/usr/bin:/bin"]
    cmd = [*mounts, str(archiver), "rcsD", "--format=gnu", "/out/" + leaf, *("/inputs/" + name for name in names)]
    run = subprocess.run(cmd, capture_output=True)
    (output_dir.parent/(output_dir.name + ".stderr")).write_bytes(run.stderr)
    assert run.returncode == 0 and not run.stdout, (run.returncode, run.stderr[-1500:])
    assert list(output_dir.iterdir()) == [output_dir/leaf]
    return output_dir/leaf


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("capture", type=Path)
    parser.add_argument("actual", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--arm", choices=("A", "B"), required=True)
    args = parser.parse_args()
    source, actual, output = (p.resolve(strict=True) for p in (args.capture, args.actual, args.output))
    assert not list(output.iterdir())
    assert stat.S_ISREG(actual.lstat().st_mode) and actual.name.startswith("libruff_linter")
    archiver = Path("/usr/bin/llvm-ar-18")
    assert archiver.is_file()
    events = [line.split("\t") for line in (source/"events.tsv").read_text().splitlines()]
    assert events[-1] == ["terminal", "0", "1", "258", "1", str(int(args.arm == "B"))], events[-1]
    selected, = [e for e in events if e[0] == "selected"]
    published, = [(i, e) for i, e in enumerate(events) if e[0] == "publish"]
    assert Path(published[1][3]) == actual and Path(published[1][2]).name == "tmp.a"
    clones = [(i, e) for i, e in enumerate(events) if e[0] == "clone"]
    assert len(clones) == int(args.arm == "B")
    if clones:
        i, clone = clones[0]
        assert clone[2:5] == ["0", "1", "1"] and i < published[0] and clone[6] == published[1][2]
    execs = [e for e in events if e[0] == "exec"]
    assert [int(e[1]) for e in execs] == list(range(len(execs)))
    signatures = []
    jobs = []
    child_rc = {e[1]: int(e[2]) for e in events if e[0] == "exit"}
    for _, seq, pid, compiler, exe, target in execs:
        raw = (source/("exec-" + seq + ".argv")).read_bytes()
        assert raw.endswith(b"\0")
        argv = [os.fsdecode(s) for s in raw[:-1].split(b"\0")]
        if compiler == "1":
            assert child_rc[pid] == 0
            if target:
                assert any(a.startswith("--emit=") and "link" in a.split(",") for a in argv)
                jobs.append(target)
                role = "full"
            else:
                role = "query"
                assert args.arm == "B" and argv[1:] == ["-Zohm-rlib-origin=.", "--print=sysroot"]
            hints = [x for x in argv if x.startswith("-Zohm-rlib-origin=")]
            if target:
                assert len(hints) == int(args.arm == "B" and target == "ruff_linter")
                if target == "ruff_linter":
                    assert pid == selected[1]
            norm = [a for a in argv if a not in hints]
            signatures.append({"role": role, "target": target, "raw_sha256": hashlib.sha256(raw).hexdigest(),
                               "without_origin_sha256": hashlib.sha256(b"\0".join(map(os.fsencode, norm)) + b"\0").hexdigest()})
        assert Path(exe).name not in {"cc", "gcc", "collect2", "wild", "wild-linker", "ld.bfd", "ld.lld"}, exe
    expected_jobs = "ruff_db ruff_linter ruff_python_ast ruff_python_codegen ruff_python_importer ruff_python_index ruff_python_literal ruff_python_parser ruff_python_semantic ruff_ranged_value".split()
    assert sorted(jobs) == expected_jobs, sorted(jobs)
    # Cargo caches the support query, so the startup state can determine whether B needs it.
    assert sum(r["role"] == "query" for r in signatures) <= int(args.arm == "B")
    acquired = [e for i, e in enumerate(events) if e[0] == "input" and i < published[0]]
    assert len(acquired) == 258
    inputs = output/"inputs"
    inputs.mkdir()
    manifest = []
    for i, (_, index, _, dev, ino, length, path) in enumerate(acquired):
        name = Path(path).name
        source_file = source/("input-" + index)
        assert i == int(index) and int(length) == source_file.stat().st_size and int(dev) > 0 and int(ino) > 0
        assert not (inputs/name).exists()
        link_or_copy(source_file, inputs/name)
        manifest.append({"name": name, "size": int(length), "sha256": sha(source_file)})
    names = [r["name"] for r in manifest]
    assert names[:2] == ["lib.rmeta", "lib.rmeta-link"] and len(set(names)) == 258
    pattern = rb"ruff_linter-[a-z0-9]+\.[a-z0-9]+\.[a-z0-9]+\.rcgu\.o"
    assert [s.decode() for s in re.findall(pattern, (inputs/names[1]).read_bytes())] == names[2:]
    positive = output/"reference"
    positive.mkdir()
    oracle = isolated_writer(archiver, names, inputs, positive, actual.name)
    actual_hash, oracle_hash = sha(actual), sha(oracle)
    equal = filecmp.cmp(actual, oracle, shallow=False)
    receipt = {"arm": args.arm, "bytes": actual.stat().st_size, "product_sha256": actual_hash,
               "oracle_sha256": oracle_hash, "whole_file_equal": equal, "member_inputs": manifest,
               "compiler_invocations": signatures, "capture_sha256": sha(source/"events.tsv"),
               "llvm_ar_sha256": sha(archiver), "successful_target_clones": len(clones),
               "archive_members": list(archive_members(oracle)), "controls": {}}
    report = output/"result.json"
    def save():
        report.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    save()
    assert equal and actual_hash == oracle_hash, (actual_hash, oracle_hash)
    members = receipt["archive_members"]
    assert [m["name"] for m in members] == ["/", "//", *names]
    assert all(all(m[k] == row[k] for k in ("name", "size", "sha256")) for m, row in zip(members[2:], manifest))
    for label in ("object-name", "metadata-byte"):
        altered = output/(label + "-inputs")
        altered.mkdir()
        ctrl_names = names[:]
        if label == "object-name":
            old = names[2]
            ctrl_names[2] = ("x" if old[0] != "x" else "y") + old[1:]
        for original, new in zip(names, ctrl_names):
            if label == "metadata-byte" and original == "lib.rmeta":
                data = bytearray((inputs/original).read_bytes())
                # Flip the first byte after the private Rust metadata signature inside the ELF wrapper.
                signature = b"rust\0\0\0"
                loc = data.index(signature) + len(signature)
                assert loc < len(data) and data.startswith(b"\x7fELF")
                data[loc] ^= 1
                (altered/new).write_bytes(data)
            else:
                link_or_copy(inputs/original, altered/new)
        dest = output/(label + "-output")
        dest.mkdir()
        modified = isolated_writer(archiver, ctrl_names, altered, dest, actual.name)
        checksum = sha(modified)
        assert checksum not in {actual_hash, *receipt["controls"].values()} and not filecmp.cmp(modified, actual, shallow=False)
        receipt["controls"][label] = checksum
        save()
        modified.unlink()
    assert all(sha(inputs/r["name"]) == r["sha256"] for r in manifest)
    assert sha(actual) == sha(oracle) == actual_hash
    print(f"{args.arm}: independent writer matched all {actual.stat().st_size:,} bytes from 258 acquired source files. Two changed-input controls differed.")


if __name__ == "__main__":
    main()
