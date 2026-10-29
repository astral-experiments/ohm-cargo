"""Verify the supplemental output census and optionally re-read the retained pair of native files."""
from pathlib import Path
import argparse
import collections
import hashlib
import json
import re
import struct

if not __debug__:
    raise SystemExit("Run with assertions enabled")

def h(b):
    return hashlib.sha256(b).hexdigest()

def sections(b):
    assert b[:6]==b"\x7fELF\x02\x01"
    sh=struct.unpack_from("<Q",b,40)[0]
    sz,num,st=struct.unpack_from("<HHH",b,58)
    assert st<num and sz==64 and sh+sz*num<=len(b)
    entries=[struct.unpack_from("<IIQQQQIIQQ",b,sh+i*sz) for i in range(num)]
    name_start=entries[st][4]
    name_end=name_start+entries[st][5]
    ranges=[]
    for e in entries:
        assert e[0]<entries[st][5]
        loc=name_start+e[0]
        name=b[loc:b.index(0,loc,name_end)].decode("ascii")
        if e[1] not in (0,8) and e[5]:
            ranges.append((e[4],e[4]+e[5],name))
    return b[sh:sh+sz*num],sorted(ranges)

def delta(a,b):
    assert len(a)==len(b)
    tables, intervals=sections(a)
    assert (tables,intervals)==sections(b)
    result={}
    def analyze(name,lo,hi):
        aa,bb=a[lo:hi],b[lo:hi]
        diffs=[lo+i for i,(x,y) in enumerate(zip(aa,bb)) if x!=y]
        if diffs:result[name]={"start":lo,"size":hi-lo,"mismatched_bytes":len(diffs),"first_offset":diffs[0],"last_offset":diffs[-1],
                               "A_sha256":h(aa),"B_sha256":h(bb)}
    pos=0
    diagnostics={}
    for lo,hi,name in intervals:
        assert pos<=lo<=hi<=len(a)
        analyze("outside before "+name,pos,lo)
        analyze(name,lo,hi)
        pos=hi
        if name==".rodata":
            regex=rb"`(ignore|size_fn|size)` conflicts with mutually exclusive `(ignore|size_fn|size)`"
            for arm,blob in [("A",a),("B",b)]:
                diagnostics[arm]=[{"offset":lo+m.start(),"argument":m[1].decode(),"conflicts_with":m[2].decode()} for m in re.finditer(regex,blob[lo:hi])]
    analyze("after final section",pos,len(a))
    return result,diagnostics

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("functional",type=Path,help="the accompanying original 12-phase component")
    parser.add_argument("files",nargs="*",type=Path,help="optionally, the original A.so and B.so")
    args=parser.parse_args()
    assert len(args.files) in (0,2)
    root=Path(__file__).resolve().parent
    r=json.loads((root/"sections.json").read_bytes())
    assert h((args.functional/"SHA256SUMS").read_bytes())==r["source_functional_manifest"]=="cc25e2379d12a2faa95c5a2f710a10de5eacb474a46a1ad6f8b64d53677c207d"
    indexes=[]
    for arm in "AB":
        name="cold-native/"+arm+".json"
        raw=(args.functional/name).read_bytes()
        assert h(raw)+"  "+name in (args.functional/"SHA256SUMS").read_text().splitlines()
        proc=json.loads(raw)["wild_outputs"]
        assert len(proc)==188 and all(row["exit"]==0 and row["status"]=="retained" for row in proc)
        idx={row["path_sha256"]:row for row in proc};assert len(idx)==188
        indexes.append(idx)
        claimed=r["physical_subjects"][arm]
        assert {k:idx[claimed["path_sha256"]][k] for k in claimed}==claimed
    a,b=indexes
    assert a.keys()==b.keys()
    different=[key for key in a if (a[key]["size"],a[key]["sha256"])!=(b[key]["size"],b[key]["sha256"])]
    assert different==[r["physical_subjects"]["A"]["path_sha256"]]
    assert r["empty_A_B_complete_native_path_counts"]=={"compared":188,"equal":187,"different":1}
    assert r["registered_cold_outputs"]=={"compared":52,"equal":52} and r["identical_section_headers"] and r["all_other_bytes_equal"]
    assert r["path"]==a[different[0]]["file"]==b[different[0]]["file"]=="libget_size_derive2-7de3207bd8fa1d6e.so"
    changes=r["differing_ranges_by_section"]
    assert {k:v["mismatched_bytes"] for k,v in changes.items()}=={".note.gnu.build-id":32,".rodata":191,".text":45,".rustc":32}
    for value in changes.values():
        assert value["start"]<=value["first_offset"]<=value["last_offset"]<value["start"]+value["size"]
        assert value["A_sha256"]!=value["B_sha256"]
    literals=r["literal_mutually_exclusive_diagnostics_by_rodata_order"]
    pairs={a:[(e["argument"],e["conflicts_with"]) for e in es] for a,es in literals.items()}
    assert len(set(pairs["A"]))==6 and set(pairs["A"])==set(pairs["B"]) and pairs["A"]!=pairs["B"]
    if args.files:
        left,right=[f.read_bytes() for f in args.files]
        assert h(left)==a[different[0]]["sha256"] and h(right)==b[different[0]]["sha256"]
        assert delta(left,right)==(changes,literals)
    else:
        control=Path("/bin/true").read_bytes();intervals=sections(control)[1]
        assert delta(control,control)[0]=={}
        start,_,_ = next(e for e in intervals if e[2]==".text")
        changed=bytearray(control);changed[start]^=1
        assert delta(control,bytes(changed))[0][".text"]["mismatched_bytes"]==1
    print("Verified 188 exact cold paths, 187 equal files, one compiler plugin with 300 differing bytes in four sections.")
if __name__=="__main__":main()
