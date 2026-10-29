"""Check the published syscall, native command, Cargo verdict and artifact projections."""
import argparse
from collections import Counter
import copy
import gzip
import hashlib
import json
import os
from pathlib import Path
import re


ROOT = Path(__file__).resolve().parent
EXPECTED = {
    "A": ("5394ce8817e224971230b80a9066cc28d504ff94", "3157f963855bcd1cdc9c5512611aaf81bdf8b984",
          "aa886cc519dd9f1cd97db76c52228dde1b25d08d3b367c067211aa42bc472add"),
    "B": ("b29c83670833857c43cc01a0d530b4048db2187b", "b2a9f0679ac0a2cf5e6c251e0d076b690b0a1c41",
          "5da7510ae4363877fc04504c2b4b054630b8290f2431be3b19701c90e62f6ac0"),
}
REPORTS = {
    "some-empty", "some-named", "missing-notification", "retrain", "default", "enable", "producer",
    "consume", "explicit-fresh", "explicit-together", "real-link-prime", "real-link-public-edit", "real-link-fresh",
}
WRAPPERS = {
    # Expected command exit, actual result inside the compiler wrapper, public program result.
    "default/cold": (0, 17, 17), "default/remove-executable": (101, 29, 17),
    "default/recover-executable": (0, 29, 29), "default/bitcode-cleanup": (0, 31, 31),
    "default/bad-bitcode": (101, 32, 31), "default/object-symlink": (101, 33, 31),
    "default/object-fifo": (101, 34, 31), "default/object-permission": (101, 35, 31),
    "default/recipe-symlink": (101, 36, 31), "default/recipe-fifo": (101, 37, 31),
    "default/recipe-missing": (101, 38, 31), "default/restore-supplied-manifest": (0, 39, 39),
    "default/zero-objects": (0, 40, 39), "default/recover-zero-objects": (0, 41, 41),
    "default/manifest-dir": (101, 42, 41), "explicit-no/cold": (0, 17, 17),
    "explicit-no/remove-executable": (0, 29, 17), "explicit-no/recover": (0, 30, 30),
}
CASES = {f"{mode}/{phase}" for mode in ("dev","noinc") for phase in ("cold","fresh","edit","edit-fresh")}


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def is_digest(value):
    return isinstance(value, str) and re.fullmatch("[a-f0-9]{64}", value)


def load(name):
    raw = (ROOT / name).read_bytes()
    return json.loads(gzip.decompress(raw) if name.endswith(".gz") else raw)


def work_counts(row):
    return Counter(tool for tid, order, tool, target, raw in row["programs"] if tool != "query")


def check_streams(row):
    threads = {tid: (size, digest) for tid, size, digest in row["threads"]}
    assert len(threads) == len(row["threads"]) and threads
    assert all(size >= 0 and is_digest(digest) for size, digest in threads.values())
    for tid, order, *_fields, digest in row["programs"] + row["events"]:
        assert tid in threads and order >= 0 and is_digest(digest)


def artifact_names(row):
    return {name: fresh for name, _kind, _types, fresh, _exe in row["cargo"]["artifacts"]}


def aggregate_io(events):
    totals = Counter()
    by_file = Counter()
    for _tid, _order, kind, name, op, rc, flags, error, _commitment in events:
        if op.startswith("unlink") and kind == "manifest":
            assert (rc == 0 and error is None) or (rc == -1 and error == "ENOENT")
            totals["manifest.unlink." + ("present" if rc == 0 else "missing")] += 1
        if rc < 0:
            continue
        if op.startswith("open"):
            direction = "RO" if flags.startswith("R") else "WO"
            totals[f"{kind}.open.{direction}"] += 1
            if kind in ("object", "recipe"):
                assert flags == "RNB"
        elif op in ("read", "pread64", "readv"):
            totals[kind + (".read" if rc else ".eof")] += 1
            totals[kind + ".read.bytes"] += rc
            by_file[name] += rc
        elif op in ("write", "writev", "pwrite64"):
            totals[kind + ".write"] += 1
            totals[kind + ".write.bytes"] += rc
        elif kind == "manifest" and op.startswith("rename"):
            totals["manifest.published"] += 1
    return totals, by_file


def check_history(arm, case, row):
    fresh = case.endswith("fresh")
    counts = work_counts(row)
    assert counts == ({} if fresh else {"compile": 2, "stock-wild": 1})
    assert artifact_names(row) == {"viewer": fresh, "ruff_text_size": fresh}
    total, by_file = aggregate_io(row["events"])
    assert dict(total) == row["original_mechanism"]
    retained = {Path(n).name: item for n, item in row["retained"].items()}
    objects = {n for n in retained if n.endswith(".o")}
    assert len(objects) == row["objects"] and "viewer.rlink" in retained
    assert ("viewer.rlink-cache.json" in retained) == (arm == "A")
    for n in objects | {"viewer.rlink"}:
        assert by_file[n] == (retained[n]["bytes"] if arm == "A" and not fresh else 0)
    assert total["recipe.open.RO"] == int(not fresh)
    assert total["object.open.RO"] == (len(objects) if not fresh else 0)
    published = arm == "A" and not fresh
    assert total["manifest.published"] == int(published)
    assert total["manifest.write.bytes"] == (retained["viewer.rlink-cache.json"]["bytes"] if published else 0)
    if arm == "B":
        assert total["manifest.unlink.missing"] == (0 if fresh else 2)
    return (total["object.read.bytes"] + total["recipe.read.bytes"], total["manifest.write.bytes"])


def check_wrapper(arm, case, row):
    v, w = row["verdict"], row["after_compiler"]
    exit_code, inner, outer = WRAPPERS[case]
    assert (v["cargo_exit"], w["inner_program"], v["old_public_value"]) == (exit_code, inner, outer)
    assert v["rustc_exit"] == w["inner_status"] == 0 and v["native_links"] == 1
    assert v["inner_program"] == v["compiler_requested_value"] == inner
    assert bool(row["cargo"]["finished"]["success"]) == (exit_code == 0)
    assert work_counts(row) == {"compile": 1, "stock-wild": 1} and is_digest(v["public_elf_sha256"])
    if case.endswith(("object-symlink","recipe-symlink","object-permission","recipe-missing")):
        wanted = "ELOOP" if case.endswith("symlink") else "EACCES" if case.endswith("permission") else "ENOENT"
        assert any(op.startswith("open") and flags == "RNB" and error == wanted
                   for _t, _n, _k, _f, op, _rc, flags, error, _h in row["events"])
    if case.endswith("fifo"):
        assert any("expected a regular file" in line for line in v["diagnostics"])
    if case.endswith(("bitcode-cleanup","bad-bitcode")):
        errno = "EISDIR" if case.endswith("bad-bitcode") else None
        assert any(kind == "bitcode" and op.startswith("unlink") and err == errno
                   for _t, _n, kind, _f, op, _rc, _fl, err, _h in row["events"])
    if case.endswith("restore-supplied-manifest"):
        assert v["post_manifest"] == ("regular" if arm == "A" else "missing") and w["preexisting_manifest"] is None
    if case == "default/zero-objects":
        assert v["post_manifest"] == "missing"


def check_report(arm, label, row, rows):
    got = work_counts(row)
    v = row["verdict"]
    assert got == Counter({k: v["counts"][f] for k, f in
                           [("compile","rustc_full"),("link-only","rustc_link_only"),("stock-wild","true_wild")]})
    if label in ("some-empty","some-named","missing-notification","retrain"):
        prior = [] if label in ("some-empty","missing-notification") else ["proofcase"]
        w = row["after_compiler"]
        assert row["runtime"]["passed"] == 1 and w["compiler_rc"] == 0 and v["real"] == prior
        assert [x["unused_extern_names"] for x in w["all_real_records"]] == [prior]
        if label == "missing-notification":
            assert w["dropped"] and w["injected_final_sha"] == w["injected_source_sha"] == rows[arm+"/proof/some-named"]["raw_manifest"]
            assert v["present"] == (arm == "A") and v["proof"] is None
            assert "unused_extern_names" not in row.get("manifest", {})
        else:
            assert not w["dropped"] and v["present"] and row["manifest"]["unused_extern_names"] == v["proof"] == prior
    if label == "default":
        assert v["present"] == (arm == "A") and v["program"] == 17
    if label in ("enable","consume","explicit-fresh","explicit-together"):
        assert v["present"] and row["manifest"]["objects"] and "unused_extern_names" not in row["manifest"]
        assert v["program"] == {"enable":17,"consume":29,"explicit-fresh":29,"explicit-together":31}[label]
    if label in ("explicit-together","real-link-public-edit"):
        assert got == {"compile":1,"link-only":1,"stock-wild":1}
    if label in ("real-link-prime", "real-link-public-edit","real-link-fresh"):
        assert row["manifest"]["unused_extern_names"] == ["nativecase"] and row["runtime"]["passed"] == 1
    if label in ("real-link-fresh","explicit-fresh"):
        assert not got


def temporary_args(event):
    """Identify only the compiler-created roles observed at the linker entry."""
    args = event["logical"]
    tool = event["tool"]
    roles = {}
    for i, arg in enumerate(args):
        if arg.endswith("/symbols.o"):
            role, path = "object", Path(arg)
        elif arg.endswith("/raw-dylibs"):
            role, path = "directory", Path(arg.removeprefix("-L"))
            assert (tool == "gcc" and args[i-1] == "-L") or (tool != "gcc" and arg.startswith("-L<WORK>/"))
        elif arg.startswith("-plugin-opt=-fresolution="):
            role, path = "resolution", Path(arg.split("=",2)[-1])
            assert path.parent.name == "temp" and re.fullmatch(r"cc[\w-]+\.res",path.name)
        else:
            continue
        if role in ("directory","object"):
            assert path.parent.parent == Path(event["out"]).parent and re.fullmatch(r"rustc[\w]+",path.parent.name)
        assert role not in roles.values()
        roles[i] = role
    assert set(roles.values()) == ({"object","directory"} if tool == "gcc" else {"object","directory","resolution"})
    return roles


def vector_pair(case, a, b):
    profiles = []
    for row in (a,b):
        ev = {}
        for e in row["vectors"]:
            assert e["exit"] == 0 and is_digest(e["raw"])
            args = e["logical"]
            if args is None:
                assert e["tool"] in ("cargo", "rustc-query")
                continue
            assert len(args) == e["argc"] and sha(b"\0".join(os.fsencode(x) for x in args)+b"\0") == e["logical_sha256"]
            key=(e["tool"],e["target"]); assert key not in ev
            ev[key]=e
        profiles.append(ev)
    ea, eb = profiles
    assert ea.keys() == eb.keys()
    if case.endswith("fresh"):
        assert not ea
        return
    assert set(ea) == {("rustc-full","viewer"),("rustc-full","ruff_text_size"),("gcc",None),("collect2",None),("stock-wild",None)}
    for key, x in ea.items():
        y = eb[key]
        if key[0] == "rustc-full":
            assert x["raw"] == y["raw"] and x["logical"] == y["logical"]
            continue
        roles = temporary_args(x)
        assert roles == temporary_args(y) and x["argc"] == y["argc"]
        assert x["raw"] != y["raw"] and x["transient_bytes"] == y["transient_bytes"]
        if key[0] == "stock-wild":
            temp=x["transient_bytes"]
            assert temp["raw_dylibs"] == [] and temp["resolution_len"] == 0 and temp["resolution"] == sha(b"")
            assert temp["object_len"] > 0 and is_digest(temp["object"])
        diffs = []
        for i,(one,two) in enumerate(zip(x["logical"],y["logical"],strict=True)):
            if i in roles or one == two:
                continue
            left, right = Path(one), Path(two)
            assert case.startswith("dev/") and left.parent == right.parent and left.parent.name == "viewer.rlink-objects"
            pa,pb=left.name.split("."),right.name.split(".")
            assert pa[:-3] == pb[:-3] and pa[-2:] == pb[-2:] == ["rcgu","o"] and pa[-3] != pb[-3]
            assert all(re.fullmatch("[a-z0-9]+",s) for s in (pa[-3],pb[-3]))
            prefix=Path("<WORK>")/case.split("/")[0]
            assert a["retained"][str(left.relative_to(prefix))] == b["retained"][str(right.relative_to(prefix))]
            diffs.append(i)
        expected = 0 if case.startswith("noinc") else 12 if case.endswith("cold") else 9
        assert len(diffs) == expected


def verify(basis, rows):
    assert basis["private_manifest"] == "eb5f9eaea741704c26d78d0780f43746d999763dd71c19c0a3f6aa0886ac8c78"
    assert basis["private_verified"] == "b5883afa71c16e222b9a04e51e6e522ea5b63371ac39fa74432b7a83d67cb402"
    assert basis["plan"]["git"] == "cbbd64db83ce4bb43ba5f00a84ed6008c7c20c44"
    assert len(rows) == sum(s["count"] for s in basis["sections"].values()) == 94
    src = {}
    for tag, s in basis["upstream"].items():
        src[tag] = {f:sha(t.encode()) for f,t in load(tag+"-sources.json.gz").items()}
        assert len(src[tag]) == 6 and src[tag] == s["files"]
    assert src["old"].keys() == src["new"].keys() and [k for k in src["old"] if src["old"][k] != src["new"][k]] == ["crates/ruff_text_size/src/size.rs"]
    totals = Counter()
    io = {}
    for arm in "AB":
        s=basis["subjects"][arm]
        assert (s["source"],s["tree"],s["binary"]) == EXPECTED[arm]
        assert (s["ordered_externs"],s["linker_inputs"],s["rlibs"]) == (239,335,326)
        assert s["profile"] == "481ada8a40c70dad11b3c7e8871e9a52207d78447ca5e8ace06fc4aec2d2b5a7"
        assert s["rustc"] == "fa2ed3ec44adb4455d5323c4ee582becd5307cb4aae6b5cfc3cdc289b3140512"
        assert s["driver"] == "d8adcc610bdae225344ed1310ff9708784634d1fecafa600f7758a5d48d2cc95"
        assert s["wild"] == "0d6335808b647d499f3d74993b602e64ff0625206c809bf4913c487eea380cd5"
        for group, expected in [("wrapper",set(WRAPPERS)),("history",CASES),("vector",CASES),("proof",REPORTS)]:
            by={k.split("/",2)[2]:v for k,v in rows.items() if k.startswith(f"{arm}/{group}/")}
            assert set(by) == expected
            for case,row in by.items():
                assert all(is_digest(row[k]) for k in ("result","raw_stdout","raw_stderr"))
                if group != "vector":
                    check_streams(row);totals[group] += len(row["threads"])
                if group != "wrapper":
                    assert row["cargo"]["finished"] == {"reason":"build-finished","success":True}
                if group == "wrapper":
                    check_wrapper(arm,case,row)
                elif group == "proof":
                    check_report(arm,case,row,rows)
                else:
                    assert row["program"] == (71 if case.split("/")[1] in ("cold","fresh") else 0)
                    assert row["program_raw"] == sha(f"{row['program']}\n".encode())
                    assert artifact_names(row) == {n:case.endswith("fresh") for n in ("viewer","ruff_text_size")}
                    assert is_digest(row["elf"][1])
                    if group == "history":io[arm,case] = check_history(arm,case,row)
    assert totals == {"history":538,"wrapper":1240,"proof":902}
    for case in CASES:
        a,b = (rows[arm+"/vector/"+case] for arm in "AB")
        vector_pair(case,a,b)
        e = a["elf"]; assert e == b["elf"] == rows["A/history/"+case]["elf"] == rows["B/history/"+case]["elf"]
        if case.endswith("fresh"):
            assert io["A",case] == io["B",case] == (0,0)
    assert io["A","dev/edit"] == (43317,3486) and io["A","noinc/edit"] == (24311,1249)
    assert io["B","dev/edit"] == io["B","noinc/edit"] == (0,0)
    for case in WRAPPERS:
        a,b=(rows[arm+"/wrapper/"+case] for arm in "AB")
        assert a["after_compiler"]["executable"] == b["after_compiler"]["executable"]
        assert a["verdict"]["public_elf_sha256"] == b["verdict"]["public_elf_sha256"]
    for case in REPORTS:
        a,b=(rows[arm+"/proof/"+case]["verdict"] for arm in "AB")
        assert all(a.get(f)==b.get(f) for f in ("elf","program","proof","counts"))
    stop=basis["preflight"]["A-proof-v1"]
    assert stop["admitted"] == 0 and stop["exit"] == 1 and stop["exception"] == "KeyError: 'executable'"
    assert stop["cargo_finished"] == {"reason":"build-finished","success":True}
    assert "compiler-message" in stop["message_kinds"] and "compiler-artifact" in stop["message_kinds"]
    if (ROOT/"portable-replay-smoke.json").is_file():
        smoke = load("portable-replay-smoke.json")
        fields = ["phase","value","fresh","elf_sha256","objects","recipe_bytes","optional_manifest","cargo_sha256"]
        for arm, entry in smoke.items():
            commands = [{k:r[k] for k in fields} for r in entry["commands"]]
            assert sha((json.dumps(commands,indent=2)+"\n").encode()) == entry["raw_result"]
            assert sha(("".join(json.dumps(r,sort_keys=True)+"\n" for r in commands)).encode()) == entry["raw_stdout"]
            assert entry["raw_stderr"] == sha(b"")
            for c,phase in zip(commands,("cold","fresh","edit","edit-fresh"),strict=True):
                row=rows[f"{arm}/history/dev/{phase}"]
                assert c["value"] == row["program"] and c["elf_sha256"] == row["elf"][1]
                assert c["fresh"] == phase.endswith("fresh") and c["optional_manifest"] == (arm == "A")
    return totals


def self_test(basis, rows):
    def reject(change):
        altered=copy.deepcopy(rows)
        change(altered)
        try: verify(basis,altered)
        except (AssertionError,KeyError):return
        raise AssertionError("mutated projection was accepted")
    def alter_read(x):
        reads=x["A/history/dev/edit"]["events"]
        next(e for e in reads if e[2]=="recipe" and e[4]=="read" and e[5]>0)[5]-=1
    def alter_arg(x):
        event=next(e for e in x["B/vector/noinc/edit"]["vectors"] if e["tool"]=="gcc")
        event["logical"][1]="-m32"
        event["logical_sha256"]=sha(b"\0".join(os.fsencode(t) for t in event["logical"])+b"\0")
    reject(alter_read);reject(alter_arg)
    reject(lambda x:x["B/proof/some-empty"]["manifest"].pop("unused_extern_names"))
    reject(lambda x:x["B/proof/missing-notification"]["after_compiler"].update(injected_final_sha="0"*64))
    reject(lambda x:x["B/wrapper/default/remove-executable"]["verdict"].update(cargo_exit=0))
    reject(lambda x:x.pop("A/history/dev/fresh"))
    print("6 modified projections rejected")


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--self-test",action="store_true")
    args=parser.parse_args()
    basis,rows=load("subjects.json"),load("commands.json.gz")
    counts=verify(basis,rows)
    print(f"94 Cargo commands, {sum(counts.values())} syscall streams, 16 native argv acquisitions")
    print("Incremental edit saved 43317 bytes read and 3486 bytes written")
    print("Nonincremental edit saved 24311 bytes read and 1249 bytes written")
    if args.self_test:self_test(basis,rows)
