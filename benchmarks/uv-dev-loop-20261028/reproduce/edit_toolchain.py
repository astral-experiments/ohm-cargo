"""Select and audit private Cargo and Wild binaries for the all-components holdout."""
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess

from measure import BENCH, RUST, WORK, digest


def elf(path):
    info = path.stat()
    with path.open("rb") as f:
        header = f.read(20)
    if (path.is_symlink() or not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid()
            or not info.st_mode & 0o111 or info.st_mode & 0o6000
            or header[:6] != b"\x7fELF\x02\x01" or header[16:18] not in (b"\x02\0", b"\x03\0")
            or header[18:20] != b"\x3e\0"):
        raise ValueError(f"expected an owned, executable x86-64 ELF at {path}")
    return digest(path)


def switch(source, slot):
    temporary = slot.with_suffix(".holdout-next")
    os.link(source, temporary)
    os.replace(temporary, slot)
    temporary.unlink(missing_ok=True)
    if not slot.samefile(source):
        raise RuntimeError(f"wrong executable at {slot}")


class MatchedToolchain:
    def __init__(self, args, root, out, cargo):
        self.plan = json.loads(args.toolchain_plan.read_text())
        self.root, self.out, self.cargo = root, out, cargo
        if (not args.workspace or args.mode != "wall" or not args.cargo_home
                or self.plan["pairs"] != args.pairs or self.plan["cohorts"][args.study][args.endpoint] != args.seed):
            raise ValueError("parameters disagree with the all-components plan")
        if cargo != {arm: (WORK / path).resolve() for arm, path in self.plan["cargo"].items()}:
            raise ValueError("unregistered Cargo binaries")
        self.sysroot = BENCH / f"sysroot-edit-{args.study}-{args.endpoint}"
        self.link = self.sysroot / self.plan["linker_slot"]
        self.wild = {arm: (WORK / wild).resolve() for arm, (wild, _) in self.plan["wild"].items()}
        self.wild_hash = {arm: sha for arm, (_, sha) in self.plan["wild"].items()}
        if ({arm: elf(path) for arm, path in self.wild.items()} != self.wild_hash
                or elf(cargo["base"]) != self.plan["base_cargo_sha256"]):
            raise ValueError("registered ELF inputs have changed")
        self.release_link = RUST.parent / self.plan["linker_slot"]
        self.verify_release()

    def verify_release(self):
        if elf(self.release_link) != self.plan["release_wild_sha256"]:
            raise RuntimeError("the linker in the shared release changed")

    def protocol(self, plan_file):
        return dict(toolchain_plan_sha256=digest(plan_file), rustc=str(self.sysroot / "bin/rustc"),
                    rustdoc=str(self.sysroot / "bin/rustdoc"), linker=str(self.link),
                    wild_sha256=self.wild_hash, binary_seal="seal.json",
                    gate=self.plan["test"], alpha_initial=self.plan["alpha_initial"],
                    alpha_replicate=self.plan["alpha_replicate"])

    def stage(self):
        if not self.sysroot.exists():
            subprocess.run(["cp", "-a", "--reflink=auto", str(RUST.parent), str(self.sysroot)], check=True)
            self.sysroot.chmod(0o700)
        if (self.sysroot.is_symlink() or self.sysroot.stat().st_mode & 0o077
                or self.link.samefile(self.release_link) or elf(self.link) != self.plan["release_wild_sha256"]):
            raise ValueError("expected an untouched, isolated copy of released rustc")
        private_rustc = self.sysroot / "bin/rustc"
        if (elf(private_rustc) != elf(RUST / "rustc")
                or not self.sysroot.samefile(subprocess.check_output([private_rustc, "--print", "sysroot"], text=True).strip())):
            raise ValueError("private rustc has the wrong sysroot")

    def selected(self, arm, cargo_slot, cargo_hash):
        switch(self.wild[arm], self.link)
        actual = dict(cargo_sha256=elf(cargo_slot), wild_sha256=elf(self.link))
        if actual["wild_sha256"] != self.wild_hash[arm] or actual["cargo_sha256"] != cargo_hash:
            raise RuntimeError("selected Cargo or Wild differs from its frozen ELF")
        return actual

    def snapshots(self):
        summaries = []
        for name in ("seed-target", "target-base", "target-candidate"):
            tree = self.root / name
            metadata = hashlib.sha256()
            count = size = 0
            for f in sorted(tree.rglob("*")):
                s = f.lstat()
                if stat.S_ISREG(s.st_mode):
                    count += 1
                    size += s.st_size
                entry = (str(f.relative_to(tree)), s.st_mode, s.st_mtime_ns,
                         os.readlink(f) if f.is_symlink() else s.st_size if f.is_file() else 0)
                metadata.update(json.dumps(entry).encode() + b"\n")
            summaries.append(dict(files=count, bytes=size, metadata_sha256=metadata.hexdigest(),
                                  rustc_info_sha256=digest(tree / ".rustc_info.json")))
        if any(s != summaries[0] for s in summaries[1:]):
            raise RuntimeError("parked targets differ from their warmed source snapshot")
        meta = json.loads((self.out / "protocol.json").read_text())
        original = subprocess.check_output(["git", "-C", str(WORK / "uv"), "show", f"{meta['uv']}:{meta['edit_path']}"])
        source_sha = digest(self.root / "source" / meta["edit_path"])
        if hashlib.sha256(original).hexdigest() != source_sha:
            raise RuntimeError("source differs from the pristine pinned archive")
        return dict(common_target=summaries[0], pristine_source_sha256=source_sha)

    def seal(self, env, cargo_slot, checking=False):
        hashes = {arm: elf(p) for arm, p in self.cargo.items()}
        candidate = self.cargo["candidate"]
        receipt = candidate.parent.parent / "logs" / f"{candidate.name}.verified"
        verified = dict(re.findall(r"^(\S+) cargo/std ([0-9a-f]{64}) ", receipt.read_text(), re.M))
        if any(verified.get(path.name) != hashes[arm] for arm, path in self.cargo.items()):
            raise RuntimeError("Cargo lacks the matching completed standard-library build audit")
        release_driver, = (RUST.parent / "lib").glob("librustc_driver-*.so")
        rustc_driver_hash = digest(self.sysroot / "lib" / release_driver.name)
        if rustc_driver_hash != digest(release_driver):
            raise RuntimeError("the private rustc driver differs from the released library")
        data = dict(cargo_sha256=hashes, wild_sha256=self.wild_hash, owner_uid=os.getuid(),
                    cargo_build_audit_sha256=digest(receipt), private_rustc_driver_sha256=rustc_driver_hash,
                    private_rustc_sha256=elf(self.sysroot / "bin/rustc"), shared_linker_sha256=elf(self.release_link))
        seal = self.out / "seal.json"
        if seal.exists():
            if json.loads(seal.read_text()) != data:
                raise ValueError("ELFs differ from the pre-measurement seal")
            return hashes
        if checking or (self.out / "pairs.csv").exists():
            raise ValueError("a verified seal is required before taking measurements")
        snapshot = self.snapshots()
        probe = self.root / "link-probe"
        probe.mkdir(exist_ok=True)
        (probe / "Cargo.toml").write_text('[package]\nname="ohm-link-probe"\nversion="0.0.0"\nedition="2024"\n[[bin]]\nname="ohm-link-probe"\npath="main.rs"\n')
        (probe / "main.rs").write_text("fn main() {}\n")
        for arm in self.cargo:
            switch(self.cargo[arm], cargo_slot)
            self.selected(arm, cargo_slot, hashes[arm])
            trace = self.out / f"link-probe-{arm}.log"
            target = self.root / f"link-probe-{arm}-target"
            cmd = ["strace", "-f", "-s", "1024", "-e", "trace=execve", "-o", str(trace), str(cargo_slot),
                   "build", "--offline", "--target-dir", str(target)]
            subprocess.run(cmd, cwd=probe, env=env, check=True, capture_output=True)
            executed = re.findall(r'\bexecve\("([^"]+)",.*?\)\s+= 0$', trace.read_text(), re.M)
            linkers = [exe for exe in executed if Path(exe).name in ("ld.bfd", "ld", "ld.lld", "rust-lld", "wild")]
            if linkers != [str(self.link)] or str(self.sysroot / "bin/rustc") not in executed:
                raise RuntimeError(f"{arm} did not execute the expected private rustc and Wild: {linkers}")
        self.verify_release()
        (self.out / "snapshot-identity.json").write_text(json.dumps(snapshot, indent=2) + "\n")
        with seal.open("x") as f:
            f.write(json.dumps(data, indent=2) + "\n")
        return hashes
