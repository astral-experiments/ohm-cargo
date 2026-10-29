"""Read exactly the two tagged stock uv ELFs and compare all bytes."""
import hashlib
import json
import os
import struct
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROJECT = HERE.parent
WORK = PROJECT.parent
ROOT = Path((WORK/"bench-home.path").read_text().strip())/"role-studies-18/replica"
ROLE = "debug/build/uv/e6ac92541876a4a1/out/uv"
FIXED = [
    ("previous_counted_base", "rejected-test-target", 128450561, 128516869,
     "edited-roles/results/replica/test/admit-1-count-base/receipt.json",
     "37a15de60cfcbbcd9df27161565080b419c18aca5792908e5fca0dc901d858cc"),
    ("rejected_native_base", "rejected-recovery-test-target", 128715612, 128737932,
     "edited-role-recovery/results/replica/test/admit-0-native-base/receipt.json",
     "c9f698ca2c9b0673d35c560375b1751b241ac3f9cfb4ec23534aa448dc4f5b91"),
]
SIZE = 316713312


def sha(b):
    return hashlib.sha256(b).hexdigest()


def metadata(fd):
    budget = 32768
    def read(n, off):
        nonlocal budget
        assert n <= budget and 0 <= off <= SIZE - n
        budget -= n
        b = os.pread(fd, n, off)
        assert len(b) == n
        return b
    hdr = read(64, 0)
    assert hdr[:7] == b"\x7fELF\x02\x01\x01" and struct.unpack_from("<H",hdr,18)[0] == 62
    phoff, shoff = struct.unpack_from("<QQ", hdr, 32)
    phsz, phn, shsz, shn, strings = struct.unpack_from("<HHHHH", hdr, 54)
    assert shsz == 64 and 0 < strings < shn < 128 and 0 < phn < 64
    ph = read(phsz*phn, phoff)
    sh = read(shsz*shn, shoff)
    off, size = struct.unpack_from("<QQ",sh,strings*shsz+24)
    names = read(size,off)
    parts = {}
    for i in range(shn):
        at = i*shsz
        index, kind = struct.unpack_from("<II",sh,at)
        name = names[index:names.index(0,index)]
        if name == b".rodata":
            assert "rodata_sh_entsize" not in parts and kind == 1
            start = shoff + at + 56
            parts["rodata_sh_entsize"] = [start, start+8, sh[at+56:at+64].hex()]
        if name == b".note.gnu.build-id":
            assert "gnu_build_id" not in parts and kind == 7
            start, length = struct.unpack_from("<QQ",sh,at+24)
            assert length == 48
            note = read(length,start)
            assert note[:16] == struct.pack("<III",4,32,3)+b"GNU\0"
            parts["gnu_build_id"] = [start+16, start+48, note[16:].hex()]
    assert set(parts) == {"gnu_build_id","rodata_sh_entsize"}
    return {"elf_header":sha(hdr), "program_headers":sha(ph), "section_headers":sha(sh),
            "section_names":sha(names), "sections":shn, "header_bytes_read":32768-budget, "fields":parts}


def main():
    assert os.geteuid() != 0 and Path("/proc/1/comm").read_text().strip() == "systemd"
    assert os.sched_getaffinity(0) == {29}
    declare = PROJECT/"edited-roles/results/replica/test/admit-0-native-base/receipt.json"
    ref_bytes = declare.read_bytes()
    ref = json.loads(ref_bytes)
    assert ref["files"][ROLE]["sha256"] == FIXED[0][-1]
    study = PROJECT/"edited-role-next/cells/replica-test/closure.json"
    assert sha(study.read_bytes()) == "7ce6d653e7e21d5bd36d7498d048a5d787d3bee09d760fa105f3b3af9dc1eea1"
    observations, fds = {}, []
    ranges = None
    try:
        for label, bank, root_ino, file_ino, path, raw_sha in FIXED:
            root = ROOT/bank
            assert (root.stat().st_dev,root.stat().st_ino) == (64769,root_ino)
            f = root/ROLE
            fd = os.open(f, os.O_RDONLY | os.O_NOATIME | os.O_NOFOLLOW)
            fds.append(fd)
            st = os.fstat(fd)
            assert (st.st_dev,st.st_ino,st.st_size) == (64769,file_ino,SIZE)
            assert f.samefile(root/"debug/uv") and st.st_nlink == 2
            receipt_bytes = (PROJECT/path).read_bytes()
            receipt = json.loads(receipt_bytes)
            assert receipt["roster"] == ref["roster"] and receipt["actual_binary_inodes"] == ref["actual_binary_inodes"]
            assert (receipt["source_sha256"],receipt["source_mtime_ns"]) == (ref["source_sha256"],ref["source_mtime_ns"])
            assert receipt["files"][ROLE]["sha256"] == raw_sha and receipt["files"][ROLE]["size"] == SIZE
            meta = metadata(fd)
            positions = {k:tuple(v[:2]) for k,v in meta["fields"].items()}
            assert positions == {"gnu_build_id":(896,928), "rodata_sh_entsize":(316711384,316711392)}
            assert ranges in (None,positions)
            ranges = positions
            observations[label] = {"bank":str(root), "root_inode":[64769,root_ino],
                                   "regular_inode":[st.st_dev,st.st_ino], "nlink":st.st_nlink,
                                   "mode":oct(st.st_mode), "mtime_ns":st.st_mtime_ns,
                                   "receipt":path, "receipt_sha256":sha(receipt_bytes), "metadata":meta}
        raw = [hashlib.sha256(),hashlib.sha256()]
        masked = [hashlib.sha256(),hashlib.sha256()]
        groups, changed, outside = [], 0, 0
        for start in range(0,SIZE,1<<20):
            n = min(SIZE-start, 1<<20)
            parts = [os.pread(fd,n,start) for fd in fds]
            assert all(len(p)==n for p in parts)
            for i,part in enumerate(parts):
                raw[i].update(part)
                for lo,hi in ranges.values():
                    a,b = max(lo,start),min(hi,start+n)
                    if a < b:
                        part = part[:a-start] + bytes(b-a) + part[b-start:]
                masked[i].update(part)
            if parts[0] != parts[1]:
                for i,(old,new) in enumerate(zip(*parts)):
                    if old == new:
                        continue
                    off = i+start
                    changed += 1
                    outside += not any(lo<=off<hi for lo,hi in ranges.values())
                    if groups and groups[-1]["end"] == off:
                        groups[-1]["end"] += 1
                        groups[-1]["old"].append(old)
                        groups[-1]["new"].append(new)
                    else:
                        groups.append({"begin":off,"end":off+1,"old":bytearray([old]),"new":bytearray([new])})
        for g in groups:
            g["old"] = g["old"].hex()
            g["new"] = g["new"].hex()
        for i,(label,bank,_,original_ino,_,expect) in enumerate(FIXED):
            st = os.fstat(fds[i])
            obs = observations[label]
            assert (st.st_dev,st.st_ino,st.st_size,st.st_mtime_ns) == (64769,original_ino,SIZE,obs["mtime_ns"])
            assert (ROOT/bank/ROLE).stat().st_ino == original_ino
            assert raw[i].hexdigest()==expect
            obs["actual_raw_sha256"] = raw[i].hexdigest()
            obs["mask_40_bytes_sha256"] = masked[i].hexdigest()
        result = {"created_ns":time.time_ns(), "script_sha256":sha(Path(__file__).read_bytes()), "cpu":29,
                  "physical_cell":"replica-test", "supervisor_session":91078, "supervisor_chunk":"296d24",
                  "supervisor_exit":0, "subject_exit":1, "historical_gate":None, "historical_scored_rows":0,
                  "closure_sha256":sha(study.read_bytes()), "ordinary_reference":str(declare.relative_to(PROJECT)),
                  "ordinary_reference_sha256":sha(ref_bytes), "role":ROLE, "per_elf_scan_bytes":SIZE,
                  "ordinary_reference_baseline_raw_sha256":ref["files"][ROLE]["sha256"],
                  "source_sha256":ref["source_sha256"], "source_mtime_ns":ref["source_mtime_ns"],
                  "role_counts":ref["roster"]["role_counts"], "test_executables":len(ref["roster"]["tests"]),
                  "actual_tool_inodes":ref["actual_binary_inodes"], "files":observations,
                  "divergent_groups":groups, "different_bytes":changed, "different_outside_mask":outside,
                  "unchanged_bytes":SIZE-changed, "identical_after_proved_40_byte_mask":masked[0].digest()==masked[1].digest()}
        with (HERE/"stock-comparison.json").open("x") as f:
            json.dump(result,f,indent=2); f.write("\n")
        print(json.dumps({k:result[k]for k in ("per_elf_scan_bytes","divergent_groups","different_bytes","different_outside_mask","unchanged_bytes","identical_after_proved_40_byte_mask")}))
    finally:
        for fd in fds:
            os.close(fd)


if __name__ == "__main__":
    main()
