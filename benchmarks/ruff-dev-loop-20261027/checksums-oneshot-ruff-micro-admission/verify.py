"""Independently decode both sealed syscall ledgers. No measurement host is required."""
from pathlib import Path
import gzip, hashlib, json, sys
import sys
sys.path.insert(0,str(Path(__file__).resolve().parent))
import worker as w
p=Path(__file__).resolve().parent
def h(x):return hashlib.sha256(x).hexdigest()
def j(path):return json.loads(path.read_bytes())
def files():
    manifest={}
    for row in (p/"SHA256SUMS").read_text().splitlines():
        digest,name=row.split("  ",1);assert name not in manifest and not name.startswith(("/","./","../"))
        manifest[name]=digest;assert h((p/name).read_bytes())==digest
    assert set(manifest)=={str(f.relative_to(p)) for f in p.rglob("*") if f.is_file() and f.name!="SHA256SUMS" and "__pycache__" not in f.parts}
files()
b=j(p/"host.json");ad=j(p/"admission.json");proposal=j(p/"host-registration.json")
assert proposal["source_commit"]==b["source_commit"]==ad["source_commit"]==w.SOURCE_COMMIT
assert proposal["native_sha256"]==h((p/"admission.json").read_bytes()) and proposal["host_sha256"]==ad["host"]==h((p/"host.json").read_bytes())
assert proposal["performance_observations"]==ad["native_scores"]==0 and proposal["score_state"]=="locked"
assert b["work_sha256"]==h((p/"worker.py").read_bytes()) and b["core"]==14 and b["siblings"]==[14]
assert b["source_manifest"]==w.SOURCE_MANIFEST
plan=j(p/"screen-plan.json");assert h((p/"screen-plan.json").read_bytes())==b["plan"]
covered=set(b["elf_paths"])
for v in b["elf_paths"].values():assert set(v.get("needed",{}).values())<=covered
for module,file in (("drrun",w.DR),("client",w.CLIENT),("libdynamorio",w.D/"sdk/lib64/release/libdynamorio.so")):
    assert b["elf_paths"][str(file)]["sha256"]==plan["counter"][module]
assert b["elf_paths"][str(w.ELF)]["sha256"]==plan["harness"] and b["environment"]==w.NATIVE_ENV
rawcorpus=gzip.decompress((p/"corpus.json.gz").read_bytes());assert h(rawcorpus)==plan["corpus"]
corpus=json.loads(rawcorpus)["actual_inputs"];sizes=[entry["size"] for entry in corpus]
assert len(sizes)==1238 and sum(sizes)==12381544
stamps=json.loads(gzip.decompress((p/"input-identity.json.gz").read_bytes()))
assert [s[3] for s in stamps]==sizes and ad["inputs"]==h((p/"input-identity.json.gz").read_bytes())
r=j(p/"references.json");assert r["four_sweeps"]==plan["expected_stdout"] and r["sha_over_ledger"]==h(b"".join(bytes.fromhex(e["sha256"]) for e in corpus))
refr=(p/"functional"/"stdout").read_bytes()
assert h(refr)==plan["updates_at_freeze"]["corrected_output_sha256"] and r["c_arbitrary_per_file_then_over_ledger"].encode() in refr
assert h((p/"packet"/"stdout").read_bytes())==plan["updates_at_freeze"]["corrected_packet_sha256"]
assert r["compiler"]["sha256"] and r["files"].keys()=={"blake3.c","blake3_dispatch.c","blake3_portable.c","blake3.h","blake3_impl.h"}
for arm in ("before","after"):
    sn=j(p/("trace-"+arm)/"status.json");assert sn["rc"]==0
    dir=p/("trace-"+arm);record=ad["raw"][arm]
    raw=gzip.decompress((dir/"raw.txt.gz").read_bytes());assert h(raw)==record["sha_raw"]
    seq=w.read_records(raw,w.ELF,w.CORPUS,sizes);canonical=w.raw_json(seq)
    assert canonical==gzip.decompress((dir/"reads.json.gz").read_bytes()) and h(canonical)==record["sha_reads"]==ad["positive"]
    assert record["execs"]==1 and record["opens"]==record["eofs"]==len(seq)==4952
    assert [r[0] for r in seq]==list(range(1238))*4 and sum(sum(ret for _,ret in ops) for _,_,ops in seq)==record["bytes"]==49526176
    assert sum(len(ops) for _,_,ops in seq)==record["reads"]==10152
    for mode in ("ordinary-","trace-"):
        d=p/(mode+arm);assert j(d/"status.json")["rc"]==0 and (d/"stderr").read_bytes()==b"" and (d/"stdout").read_bytes()==(plan["expected_stdout"]+"\n").encode()
        inv=j(d/"invocation.json");assert inv["affinity"]==[w.CPU] and inv["environment"]==w.NATIVE_ENV and inv["argv"][-4:]==list(map(str,w.replay(arm)))
assert j(p/"capacity.json")["free_bytes"]["tmpfs"]>32*1048576
print("Verified the bound kernel, single-core host, helper and 6 DR modules/files, native C/Python oracle, 5200/96 controls, and 9,904 actual file descriptor histories. Both arms read all 49,526,176 bytes in the same 10,152 calls with 4,952 EOFs. No scores.")
