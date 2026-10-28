"""Recheck every stored native metadata binding, physical compiler roster and ordinary caller."""
from pathlib import Path
from collections import Counter
import ast, gzip, hashlib, json, re, runpy, struct, tarfile

root = Path(__file__).resolve().parent
read = lambda name: (root / name).read_bytes()
sha = lambda b: hashlib.sha256(b).hexdigest()
ledger = json.loads(read("original-records.json"))
archives = json.loads(read("retained-archive-members.json"))
wire = runpy.run_path(str(root / "wire.py"))["decode"]
blobs = {}
for f in sorted(root.glob("records-*.tar.gz")):
    with tarfile.open(f) as t:
        for entry in t:
            assert entry.isfile()
            contents = t.extractfile(entry).read()
            assert entry.name == sha(contents) and entry.name not in blobs
            blobs[entry.name] = contents
def data(name):
    v = ledger[name]
    key = v["object"]
    if key.startswith("native/"):
        b = gzip.decompress(read(key))
        assert len(b) == v["bytes"] and sha(b) == v["sha"]
        return b
    return blobs[key]
def record(name): return json.loads(data(name))
def elf_metadata(b):
    assert b[:6] == bytes.fromhex("7f454c460201")
    start = int.from_bytes(b[40:48], "little")
    width, count, names_idx = struct.unpack_from("<HHH", b, 58)
    rows = [struct.unpack_from("<IIQQQQIIQQ", b, start + width*i) for i in range(count)]
    names = rows[names_idx]
    ss = b[names[4]:names[4]+names[5]]
    md, = [row for row in rows if ss[row[0]:ss.index(0,row[0])] == b".rmeta"]
    return b[md[4]:md[4]+md[5]]
for name, v in ledger.items():
    if name.endswith("/producer.rlib"):
        ar = archives[v["sha"]]
        assert ar["retained_archive_sha"] == v["sha"]
        md, = [m for m in ar["archive_member_identifiers"] if m[0] == "lib.rmeta"]
        assert md[1:] == [ar["native_member_bytes"], v["native_member"]]
        b = gzip.decompress(read("native/"+md[2]+".elf.gz"))
        assert [len(b), sha(b)] == md[1:]
        assert elf_metadata(b) == data(name.removesuffix(".rlib") + ".rmeta")
    else:
        b = data(name)
        if v["object"] == v["sha"]:
            assert len(b) == v["bytes"]
        elif not v["object"].startswith("native/"):
            assert b"compiler-registry.invalid" in b
def header(path):
    m = re.search(rb"^private hash ([0-9a-f]{32}) stable_crate_id StableCrateId\((\d+)\)\s*\npublic_hash ([0-9a-f]{32})", data(path), re.M)
    assert m, path
    return [s.decode() for s in m.groups()]
def typed(path):
    evs = [json.loads(l) for l in data(path).splitlines()]
    assert evs[-1] == {"reason":"build-finished","success":True}
    return [v for v in evs if v["reason"] == "compiler-artifact"]
for key, candidate in [("plan.json","edit.patch"),("marker-plan.json","marker.patch"),("trivia-plan.json","trivia.patch")]:
    assert json.loads(read(key))["patch"] == sha(read(candidate))
for name in (n for n in ledger if n.startswith("whole/") and n.endswith("/result.json")):
    d = name.rsplit("/",1)[0]
    row = record(name)
    jobs = record(d+"/jobs.json")
    units = typed(d+"/cargo.stdout")
    assert row["units"] == len(units) and row["fresh"] == sum(v["fresh"] for v in units)
    assert Counter(v["kind"] for v in jobs) == row["counts"]
    assert row["cli"]["observation"][1:] == [ledger[d+"/"+fn]["sha"] for fn in ("cli.stdout","cli.stderr")]
    assert row["cli"]["observation"][0] == 1
    assert (b"F821" if row["package"]=="ruff" else b"invalid-assignment") in data(d+"/cli.stdout")+data(d+"/cli.stderr")
    for job in jobs:
        if job["kind"] == "script": continue
        raw = d+"/trace/"+str(job["pid"])
        assert ledger[raw]["sha"] == job["raw_sha"] and job["exit"] == 0 and b"+++ exited with 0 +++" in data(raw)
        exargv = re.findall(rb'execve\("(?:[^"\\]|\\.)*",\s*(\[.*?\]),\s*(?:0x[\da-f]+|NULL)', data(raw))
        assert job["args"] in [ast.literal_eval(v.decode()) for v in exargv]
        a=job["args"];part=any(v=="-Zlink-only" or (v=="-Z" and i+1<len(a) and a[i+1]=="link-only") for i,v in enumerate(a))
        if job["kind"]=="partial": assert part
        if job["kind"]=="full": assert not part
    if row["caller"] is not None:
        c = row["caller"]
        assert c["status"] == (101 if row["source"]=="reversed" else 0)
        assert [c["stdout"],c["stderr"]] == [ledger[d+"/"+f]["sha"] for f in ("reader.out","reader.err")]
    tag = d.split("/")[-1]
    if tag.startswith(("edited-","restored-")) and "repeat" not in tag:
        assert row["counts"] == {"full":13,"wild":1}
    if "repeat" in tag:
        assert row["units"] == row["fresh"] == {"ruff":373,"ty":350}[row["package"]] and not jobs
history = {}
for name in (n for n in ledger if n.startswith("whole-history/") and n.endswith("/result.json")):
    d = name.rsplit("/",1)[0]
    row = record(name); history[row["tag"]] = row
    assert header(d+"/root.txt") == [row["private"],row["stable_id"],row["public"]]
    assert row["artifacts"]["rmeta"]["sha"] == ledger[d+"/producer.rmeta"]["sha"]
    assert row["artifacts"]["rlib"]["sha"] == ledger[d+"/producer.rlib"]["sha"]
def md(tag): return history[tag]["artifacts"]["rmeta"]["sha"]
assert len(history)==10
for tags in (["actual-original","empty-original-1","empty-original-2","empty-original-3"],["actual-restored","edited-to-original","warm-forced-restored"],["empty-edited-1","empty-edited-2"]):
    assert len({md(t) for t in tags})==1
assert md("actual-original") != md("actual-restored")
assert md("original-to-edited") != md("empty-edited-1")
assert len({json.dumps(row["externs"],sort_keys=True) for row in history.values()})==1
assert len({row["argv_sha"] for row in history.values() if "argv_sha" in row})==1
aa,bb = [wire(data("whole-history/"+t+"/producer.rmeta")) for t in ("actual-original","actual-restored")]
for k in ("global","source_table","stable","expansion_hashes","def_spans","def_ident_spans"): assert aa[k]==bb[k],k
assert aa["defs"].keys()==bb["defs"].keys() and len(aa["defs"])==1099 and len(aa["expansion_hashes"])==253
different = [(v[0],bb["defs"][k][0]) for k,v in aa["defs"].items() if v[0]!=bb["defs"][k][0]]
assert len(different)==682 and len(set(different))==31
ac,bc = Counter(aa["allocations"]),Counter(bb["allocations"])
assert sum(ac.values())==181 and sum(bc.values())==189 and ac.keys()==bc.keys() and len(ac)==180
fields = b"end kind label highlight_source start line span replacement".split()
assert bc-ac == Counter(b"\0\0"+bytes([len(s)])+s+b"\0\0\1"+bytes([len(s)]) for s in fields)
for group in ("matrix","marker-matrix","trivia-matrix"):
    rows={}
    for name in (n for n in ledger if n.startswith(group+"/") and n.endswith("/result.json")):
        d=name.rsplit("/",1)[0];row=record(name);tag=row["role"];arm=row["arm"];rows[arm,tag]=row
        assert header(d+"/header.out")==row["header"]
        assert row["rmeta"]==ledger[d+"/producer.rmeta"]["sha"] and row["rlib"]==ledger[d+"/producer.rlib"]["sha"]
        units=typed(d+"/cargo.out");assert len(units)==row["units"] and sum(v["fresh"] for v in units)==row["fresh"]
        pid,=[n for n,v in ledger.items() if n.startswith(d+"/trace/run.") and v["sha"]==row["physical_trace_sha"]]
        assert b"+++ exited with 0 +++" in data(pid)
        assert data(d+"/compile-reader.err")==b"" and data(d+"/compile-reader.out")==b""
        assert row["reader"][1:]==[ledger[d+"/"+fn]["sha"] for fn in ("read.out","read.err")]
        if group=="matrix":
            if row["variant"]=="edited":
                assert row["reader"][0]==101 and b"out of bounds" in data(d+"/read.err")
            else: assert row["reader"][0]==0
        elif group=="marker-matrix":
            assert row["reader"][0]==0
            assert (b" --> cell 1:2:8" if row["variant"]=="edited" else b" ::: cell 1:2:8") in data(d+"/read.out")
        else:
            assert row["reader"][0]==0 and data(d+"/read.out")==b"3 expansion checks, tab delta 6\n"
            if tag in ("original","warm-edited","warm-restored"):
                assert row["test_harness"]["status"]==0 and b"2 passed; 0 failed" in data(d+"/test-native.out")
                v,=[v for v in typed(d+"/test-cargo.out") if v["target"]["name"]=="ruff_python_trivia" and v["executable"]]
                assert not v["fresh"]
    arms={a for a,_ in rows}
    assert len(rows)==5*len(arms) and len(arms)==(2 if group=="trivia-matrix" else 3)
    for arm in arms:
        for warm,cold in (("warm-edited","empty-edited"),("warm-restored","empty-original")):
            a,b=rows[arm,warm],rows[arm,cold]
            assert a["source"]==b["source"] and a["externs"]==b["externs"] and a["header"][:2]==b["header"][:2]
            identical=(group!="matrix" or arm=="alloc")
            assert (a["rmeta"]==b["rmeta"])==identical and (a["header"][-1]==b["header"][-1])==identical
        if group=="trivia-matrix": assert len({row["header"][-1] for (a,_),row in rows.items() if a==arm})==1
        else: assert rows[arm,"empty-edited"]["header"][-1]!=rows[arm,"empty-original"]["header"][-1]
if (root/"SHA256SUMS").exists():
    for line in read("SHA256SUMS").decode().splitlines():
        dig,n=line.split("  ",1);assert sha(read(n))==dig,n
print(f"{len(ledger)} native records, {len(archives)} privately retained rlibs, {len(blobs)} portable text objects verified")
print("Two CLI histories, forty release package compiles/callers, six unit harnesses, all eight additional serialized allocation identities verified.")

