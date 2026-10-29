"""Check the released-profile subjects, all 94 normalized observations, and two standalone replays."""
from pathlib import Path
import hashlib
import json

root = Path(__file__).resolve().parent
load = lambda name: json.loads((root / name).read_bytes())
def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()
manifest = {n:h for h,n in (line.split("  ",1) for line in (root/"SHA256SUMS").read_text().splitlines())}
assert manifest.keys() == {p.name for p in root.iterdir() if p.is_file() and p.name != "SHA256SUMS"}
assert all(sha(root/n) == h for n,h in manifest.items())
data = load("outcomes.json")
enrolled = load("subjects.json")
assert sha(root/"outcomes.json") == "41db99ab3ddc0f97a59cf2253bd5385bf0f479a915b134155f81efddcc1ca0f3"
assert data["subjects"] == enrolled["subjects"] and data["raw_archives"] == enrolled["raw_archive_sha256"]
assert len(data["raw_archives"]) == 8 and data["trace_threads"] == {"wrapper":1240,"history":538,"proof":902}
assert {k:len(data[k]["A"]) for k in ("history","vector","wrapper","proof")} == {"history":8,"vector":8,"wrapper":18,"proof":13}
commits = {"A":"8dc33c9cc641e2b641c5b8e7075652a3e9e1f70b","B":"78bedbdaafd7cda72bee7c844888b44f3b902c61"}
images = {"A":"8c1717fa9786e16d3bec0c3181c02c1803484ed857d262580ce88d54056504c5","B":"bfc45bd24c710e631ef02d0602ca895edeb2bf028215424d226e426508ceb164"}
for side,subj in data["subjects"].items():
    build=enrolled["builder"][side]
    assert build["commit"]==subj["source"]==commits[side] and build["binary_sha256"]==subj["binary"]==images[side]
    assert build["tree"]==subj["tree"] and build["complete_sha256"]==subj["complete"]
    assert (build["ordered_externs"],build["linker_inputs"],build["rlibs"])==(239,335,326)
    assert subj["wild"]=="0d6335808b647d499f3d74993b602e64ff0625206c809bf4913c487eea380cd5"
    replay=load("standalone-"+side+".json")
    assert [x["phase"] for x in replay]==["original","unchanged","edited","edited-unchanged"]
    assert [x["value"] for x in replay]==[71,71,0,0] and [x["fresh"] for x in replay]==[False,True,False,True]
    assert all(x["optional_manifest"]==(side=="A") and x["cargo_sha256"]==images[side] for x in replay)
    assert replay[0]["elf_sha256"]==replay[1]["elf_sha256"]!=replay[2]["elf_sha256"]==replay[3]["elf_sha256"]
for kind in ("history","vector","wrapper","proof"):
    a,b=data[kind]["A"],data[kind]["B"]
    assert a.keys()==b.keys()
    for name,left in a.items():
        right=b[name]
        if kind=="history":
            for key in ("fresh","program","elf","elf_bytes","objects","images"):assert left[key]==right[key]
            if name.endswith("fresh"):assert left["images"]==[] and left["fresh"]
        if kind=="vector":
            assert left["elf"]==right["elf"] and left["compiler"]==right["compiler"]
        if kind=="wrapper":assert left[:4]==right[:4]
        if kind=="proof":
            for key in ("program","counts","elf","proof"):assert left[key]==right[key]
            if name=="some-empty":assert right["proof"]==[] and right["present"]
            if name in ("explicit-together","real-link-public-edit"):assert right["counts"]=={"rustc_full":1,"rustc_link_only":1,"true_wild":1}
for phase,objects,object_bytes,recipe,manifest_bytes in [("dev/edit",9,29128,14436,3628),("noinc/edit",2,13192,11197,1301)]:
    a,b=[data["history"][s][phase] for s in ("A","B")]
    assert a["program"]==b["program"]==0 and a["images"]==["compile:ruff_text_size","compile:viewer","stock-wild"]
    assert a["syscalls"]["object.read.bytes"]==object_bytes and a["syscalls"]["recipe.read.bytes"]==recipe
    assert a["syscalls"]["manifest.write.bytes"]==manifest_bytes
    assert a["syscalls"]["object.open.RO"]==b["syscalls"]["object.open.RO"]==objects
    assert a["syscalls"]["recipe.open.RO"]==b["syscalls"]["recipe.open.RO"]==1
    assert not any(k.endswith("read.bytes") or k=="manifest.published" for k in b["syscalls"])
print("94 paired-arm command observations, 2,680 kernel thread streams and eight standalone Cargo commands verified.")
