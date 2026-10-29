from pathlib import Path
from collections import Counter
import copy,gzip,json,re,sys
ROOT=Path(__file__).resolve().parent
def valid(v):
    assert v["debug_image_sha256"]=="2eb7e548957363bfb5e4341ce1bfc312f5f5b875f881ae3d3a478531e0ddd76d"
    for m,n in (("plain",6),("inotify",12)):
        phases=v["observers"][m];assert len(phases)==n
        for stage,d in phases.items():
            before=d["metadata"]["before"];after=d["metadata"]["after"];oldfd=d["metadata"]["old_fd_after"]
            assert d["typed"]==510 and set(before)==set(after)==set(oldfd)=={"ast","index"}
            assert all(before[k][1]==after[k][1]==oldfd[k][1] for k in before)
            assert all(oldfd[k][0][:2]==after[k][0][:2]==before[k][0][:2] for k in before)
            fresh=d["fresh"];a=after["ast"][0][2];b=after["index"][0][2]
            if stage.endswith("edit"):
                assert fresh=={"ruff_python_ast":False,"ruff_python_index":False} and d["dirty"]==56 and a>b
                if m=="inotify":
                    notes=[k for e in d["events"] if e["mask"]==4 for k in e["uses"]]
                    assert notes==["index","ast"]
            elif stage.endswith("repeat-1"):
                assert fresh=={"ruff_python_ast":True,"ruff_python_index":False} and b>=a
                assert [before["ast"][0][2],before["index"][0][2]] in d["index_stale"]
            else:assert d["dirty"]==12 and all(fresh.values()) and not d["index_stale"]
            if m=="plain":assert not d["events"]
    s=v["observers"]["syscall"];assert len(s)==4
    for n,d in s.items():
        assert d["after"]["ruff_python_ast"][0]==d["after"]["ruff_python_index"][0]
        assert all(d["before"][k][1]==d["after"][k][1] for k in d["after"])
        if n.endswith("repeat"):assert d["fresh"]["ruff_python_index"]
    extras=Counter(["ty","ty_completion_bench","ty_completion_eval","ruff_benchmark","ruff_dev"])
    for direction,base_repeat in (("parent",24),("child",12)):
        for arm in ("A","B"):
            data=v["census"][arm];assert len(data)==7
            for stage in ("edit","repeat-1","repeat-2"):
                d=data[direction+"-"+stage];ev=d["events"];rs=Counter(e["role"] for e in ev)
                assert all(re.fullmatch("[0-9a-f]{64}",e["argv_sha256"]) for e in ev)
                assert d["typed"]==510 and rs["cargo"]==1
                if stage=="edit":
                    assert rs["rustc-full"]==(51 if arm=="A" else 56) and rs["stock-wild"]==rs["collect2"]==rs["gcc"]==1
                else:
                    assert rs["rustc-full"]==(base_repeat if stage=="repeat-1" and arm=="A" else 1) and rs["stock-wild"]==0
            assert data["unchanged-before"]["typed"]==510
        a=v["census"]["A"][direction+"-edit"];b=v["census"]["B"][direction+"-edit"]
        assert a["selected"]==b["selected"]
        cnt=lambda d:Counter(x["target"] for x in d["events"] if x["role"]=="rustc-full")
        assert cnt(b)-cnt(a)==extras and not cnt(a)-cnt(b)
    expected=[["ruff_python_index","E0624","method \x60is_triple_quoted_string\x60 is private",[["crates/ruff_python_index/src/multiline_ranges.rs",50,22,50,45]]]]
    for arm in ("A","B"):
        d=v["api"][arm];assert len(d)==8
        for stage,t in d.items():
            if "incompatible" in stage:assert t["result"]==101 and t["errors"]==expected
            else:assert t["result"]==0 and not t["errors"]
            if stage=="empty-repaired":assert t["dirty"]==t["typed"]==31
        assert d["repaired-unchanged"]["dirty"]==0 and d["empty-incompatible"]["dirty"]==30
if __name__=="__main__":
    v=json.loads(gzip.decompress((ROOT/"records.json.gz").read_bytes()));valid(v)
    if "--mutations" in sys.argv:
        for what in ("clock","calls","verdict"):
            w=copy.deepcopy(v)
            if what=="clock":w["observers"]["inotify"]["1-child-repeat-1"]["index_stale"]=[]
            if what=="calls":w["census"]["B"]["child-edit"]["events"].pop()
            if what=="verdict":w["api"]["B"]["incompatible"]["result"]=0
            try:valid(w)
            except AssertionError:continue
            raise AssertionError(what)
    print("Verified 22 timestamp observations, 14 warmed native censuses and 16 real Ruff visibility checks.")
