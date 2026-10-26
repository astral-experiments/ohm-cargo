"""Compare ordinary gitoxide and the verified-index subject on a private, disposable Git repository."""

import argparse, hashlib, os, subprocess
from pathlib import Path

parser = argparse.ArgumentParser(description=__doc__)
for name in ("parent", "candidate", "toolchain", "output", "collision-dir"):
    parser.add_argument("--" + name, type=Path, required=True)
parser.add_argument("--cpu", required=True)
args = parser.parse_args()
out = args.output.resolve()
out.mkdir(parents=True, mode=0o700, exist_ok=False)
repo = out / "repo"
repo.mkdir()
home = out / "cargo-home"
home.mkdir(mode=0o700)
published = args.toolchain.resolve()
subjects = {"parent": args.parent.resolve(), "candidate": args.candidate.resolve()}
for arm, cargo in subjects.items():
    t = out / arm / "toolchains/ohm"
    (t / "bin").mkdir(parents=True)
    (t / "lib").symlink_to(published / "lib", target_is_directory=True)
    for p in (published / "bin").iterdir():
        (t / "bin" / p.name).symlink_to(cargo if p.name == "cargo" else p)
baseenv = dict(
    os.environ,
    GIT_OPTIONAL_LOCKS="0",
    GIT_CONFIG_NOSYSTEM="1",
    GIT_CONFIG_GLOBAL="/dev/null",
    RUSTUP_AUTO_INSTALL="0",
    CARGO_HOME=str(home),
    CARGO_TARGET_DIR=str(out / "target"),
    CARGO_BUILD_BUILD_DIR=str(out / "shared-build"),
    CARGO_TERM_COLOR="never",
    CARGO_LOG="cargo::sources::path::verified_index=debug",
    LC_ALL="C.UTF-8",
)


def git(*args, data=None):
    return subprocess.check_output(["git", *args], cwd=repo, env=baseenv, input=data)


git("init", "-q")
index = Path(
    git("rev-parse", "--path-format=absolute", "--git-path", "index").decode().strip()
)
common = git("rev-parse", "--path-format=absolute", "--git-common-dir").decode().strip()
print("fixture", repo, common, flush=True)
(repo / "Cargo.toml").write_text(
    '[package]\nname="index-study"\nversion="0.1.0"\nedition="2021"\ndescription="local fixture"\nlicense="MIT"\n'
)
(repo / "src").mkdir()
(repo / "src/lib.rs").write_text("pub fn answer() -> u8 { 42 }\n")
(repo / ".gitignore").write_text("/ignored.local\n")
(repo / "ignored.local").write_text("ignored")
git("add", "Cargo.toml", "src", ".gitignore")
oid = git("hash-object", "-w", "--stdin", data=b"synthetic input\n").strip()


def add_index_entries(prefix, n):
    lines = [
        b"100644 "
        + oid
        + b"\t"
        + f"{prefix}/very-long-path-for-index-coverage-{i:06}/input.rs\n".encode()
        for i in range(n)
    ]
    git(
        "-c",
        "core.splitIndex=true" if prefix == "extra" else "core.splitIndex=false",
        "-c",
        "splitIndex.maxPercentChange=100",
        "update-index",
        "--index-info",
        data=b"".join(lines),
    )


add_index_entries("tracked", 4200)
assert index.stat().st_size > 256 * 1024, index.stat().st_size
original = index.read_bytes()
ts = index.stat()


def rewrite(data):
    index.write_bytes(data)
    os.utime(index, ns=(ts.st_atime_ns, ts.st_mtime_ns))


def run(arm, tag, extra=None):
    res = subprocess.run(
        [
            "taskset",
            "-c",
            args.cpu,
            "cargo",
            "+ohm",
            *(["-Zohm-defaults=no"] if tag.startswith("ohm-disabled") else []),
            "package",
            "--list",
            "--allow-dirty",
            "--offline",
        ],
        cwd=repo,
        env=dict(baseenv, RUSTUP_HOME=str(out / arm), **(extra or {})),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    (out / (tag + "-" + arm + ".stderr")).write_bytes(res.stderr)
    (out / (tag + "-" + arm + ".stdout")).write_bytes(res.stdout)
    return res


def compare(tag, expect=None, cold=False, hit=False, bypass=False, extra=None):
    a, b = (run(arm, tag, extra) for arm in subjects)
    assert a.returncode == b.returncode and a.stdout == b.stdout, (
        tag,
        a.returncode,
        b.returncode,
        a.stderr[-900:],
        b.stderr[-900:],
    )
    if expect is not None:
        assert (a.returncode == 0) == expect, (tag, a.stderr[-900:], b.stderr[-900:])
    if cold:
        assert b"hit=false" in b.stderr, (tag, b.stderr[-800:])
    if hit:
        assert b"hit=true" in b.stderr, (tag, b.stderr[-800:])
    if bypass:
        assert b"verified Git index" not in b.stderr, (tag, b.stderr[-800:])
    print(
        tag,
        "ok",
        "returncode",
        b.returncode,
        "files",
        len(b.stdout.splitlines()),
        "miss",
        b"hit=false" in b.stderr,
        "hit",
        b"hit=true" in b.stderr,
        flush=True,
    )
    return b


compare("ohm-disabled-first", True, bypass=True)
assert not (home / ".ohm-git-index-sha1dc-v1").exists()
compare("cold", True, cold=True)
compare("warm", True, hit=True)
compare("ohm-disabled-known-receipt", True, bypass=True)
corrupt = bytearray(original)
corrupt[12] ^= 0x10
rewrite(corrupt)
compare("backdated-body-corruption", False, bypass=True)
trailer = bytearray(original)
trailer[-1] ^= 0x80
rewrite(trailer)
compare("backdated-trailer-corruption", False, bypass=True)
changed = bytes(corrupt[:-20]) + hashlib.sha1(corrupt[:-20]).digest()
rewrite(changed)
compare("valid-new-body", True, cold=True)
compare("valid-new-body-warm", True, hit=True)
rewrite(original)
compare("valid-original-restored", True, hit=True)
path = repo / "untracked.rs"
path.write_text("live")
r = compare("live-untracked", True, hit=True)
assert b"untracked.rs" in r.stdout and b"ignored.local" not in r.stdout
path.unlink()
rewrite(original[:-20] + bytes(20))
compare("unsigned-index", True, bypass=True)
rewrite(original)
for threads in ("1", "0", "true", "false", "4"):
    git("config", "index.threads", threads)
    compare("index-threads-" + threads, True, hit=True)
    git("config", "--unset-all", "index.threads")
for key, val in [
    ("index.threads", "typo"),
    ("index.skipHash", "false"),
    ("gitoxide.objects.allocLimit", "1048576"),
]:
    git("config", key, val)
    compare(key, None, bypass=True)
    git("config", "--unset-all", key)
cfg = repo / ".git/config"
start = cfg.read_bytes()
cfg.write_bytes(start + b"\n[index]\n  skipHash\n")
compare("implicit-skipHash", True, bypass=True)
rewrite(corrupt)
compare("implicit-skipHash-corruption", True, bypass=True)
rewrite(original)
cfg.write_bytes(start)
git("config", "index.skipHash", "true")
rewrite(corrupt)
compare("configured-unsigned-corruption", True, bypass=True)
rewrite(original)
git("config", "--unset-all", "index.skipHash")
cache = home / ".ohm-git-index-sha1dc-v1"
for f in cache.iterdir():
    f.write_bytes(b"corrupt".ljust(32, b"\0"))
compare("tampered-certificate", True, cold=True)
for f in cache.iterdir():
    f.chmod(0o644)
compare("world-readable-certificate", True, cold=True)
cache.chmod(0o755)
compare("nonprivate-cert-directory", True, bypass=True)
cache.chmod(0o700)
for f in cache.iterdir():
    stored = out / ("receipt-" + f.name)
    f.replace(stored)
    f.symlink_to(stored)
compare("symlink-certificate", True, cold=True)
for f in cache.iterdir():
    f.unlink()
    os.mkfifo(f, mode=0o600)
compare("fifo-certificate", True, cold=True)
git("config", "core.splitIndex", "true")
git("config", "splitIndex.maxPercentChange", "100")
git("update-index", "--split-index")
compare("split-index", True, bypass=True)
add_index_entries("extra", 4200)
print("split main bytes", index.stat().st_size, flush=True)
assert index.stat().st_size > 256 * 1024
compare("large-split-index", True, bypass=True)
shared = list(index.parent.glob("sharedindex.*"))
assert shared, shared
s = shared[0]
good = s.read_bytes()
bad = bytearray(good)
bad[12] ^= 0x04
s.write_bytes(bad)
compare("tampered-split-base", False, bypass=True)
s.write_bytes(good)


# SHA-1 collision fixtures use their ordinary raw digest as the index trailer.
registry = args.collision_dir
certdir = cache
orig_stat = index.stat()
original = index.read_bytes()
before = sorted((p.name, p.lstat().st_mode) for p in certdir.iterdir())
try:
    for name in (
        "shattered-1.pdf",
        "shattered-2.pdf",
        "sha-mbles-1.bin",
        "sha-mbles-2.bin",
    ):
        raw = (registry / name).read_bytes()
        if len(raw) < 256 * 1024:
            raw += bytes(256 * 1024 - len(raw))
        digest = hashlib.sha1(raw).digest()
        index.write_bytes(raw + digest)
        os.utime(index, ns=(orig_stat.st_atime_ns, orig_stat.st_mtime_ns))
        errors = []
        for arm in subjects:
            res = run(arm, "collision-" + name)
            assert (
                res.returncode == 101
                and b"Detected SHA-1 collision attack" in res.stderr
            ), (name, arm, res.stderr)
            errors.append(res.stderr)
        assert errors[0] == errors[1], (name, errors)
        print(
            name, digest.hex(), errors[0].decode().strip().splitlines()[-1], flush=True
        )
    assert sorted((p.name, p.lstat().st_mode) for p in certdir.iterdir()) == before
finally:
    index.write_bytes(original)
    os.utime(index, ns=(orig_stat.st_atime_ns, orig_stat.st_mtime_ns))

print("All package file-list, fallback, opt-out and collision checks passed.")
