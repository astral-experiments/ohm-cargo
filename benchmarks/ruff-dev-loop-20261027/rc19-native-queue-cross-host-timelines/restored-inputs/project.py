"""Reopen the last edit native traces and their own held object files. Output uses workspace-relative names."""
from collections import Counter
from pathlib import Path
import gzip
import hashlib
import json
import os
import re
import runpy
import stat
import subprocess
import sys

root=Path(sys.argv[1]).resolve();study=root/"native-ready-order19";reports=study/"reports"
prefix="clock-v4-edit-nativeedit-trace-after-"
def fd_bytes(path):
    q=path.resolve(strict=True) if path.is_symlink() else path
    fd=os.open(q,os.O_RDONLY|os.O_NOATIME|os.O_NOFOLLOW|os.O_NONBLOCK);s=os.fstat(fd)
    def sig(x):return (x.st_dev,x.st_ino,x.st_mode,x.st_uid,x.st_gid,x.st_nlink,x.st_size,x.st_mtime_ns,x.st_ctime_ns,x.st_atime_ns)
    with os.fdopen(fd,"rb") as f:
        assert stat.S_ISREG(s.st_mode);b=f.read();assert sig(s)==sig(os.fstat(f.fileno()))==sig(q.lstat()) and len(b)==s.st_size
    return b,s
def sha(b):return hashlib.sha256(b).hexdigest()
def vector(args):return sha(b"\0".join(os.fsencode(x) for x in args)+b"\0")
def portable(b):return (json.dumps(b,sort_keys=True,separators=(",",":"))+"\n").encode()
def filemeta(a,name):
    f=Path(name);rels=f.relative_to(root);assert rels.parts[0]=="target" and ".rlink-objects" in str(rels.parent) and len(rels.parts)>4
    f=Path(paths[a]["target"])/Path(*rels.parts[1:]);b,s=fd_bytes(f)
    assert b[:4]==b"\x7fELF" and b[4:6]==b"\x02\x01" and int.from_bytes(b[16:18],"little")==1
    return {"bytes":len(b),"sha256":sha(b)},s
paths={a:json.loads(subprocess.check_output([sys.executable,"-IB",study/"native-order-lane.py","paths","qa",a])) for a in "AB"}
assert paths["A"]["namespace"]!=paths["B"]["namespace"]
comparator=root/"ops/native-order-args-v4.py"
assert sha(fd_bytes(comparator)[0])=="8f114ec372cd419e94a5f7e38f40b4667d69d8d04bd826d9b46bdde1c676d9c0"
frozen=runpy.run_path(str(comparator))["fingerprints"]
sources={};events={};matrices={};flank={};compiler={};gens={}
for a in "AB":
    d=reports/(prefix+a);raw=fd_bytes(d/"execs.json")[0];rec0=fd_bytes(d/"result.json")[0]
    ex=json.loads(raw);rec=json.loads(rec0);assert sha(raw)==rec["execs_sha256"] and ex["root_exit"]==0
    assert all(ex["process_exit"][str(e["pid"])]==0 for e in ex["events"])
    assert frozen(ex["events"],root/"target",root/"tmp")==rec["native_args"]
    events[a]={(Path(e["out"]).name,e["role"]):e for e in ex["events"] if e["role"] in ("gcc","collect2","stock-wild")}
    matrices[a]={(e["target"],e["tool"]):e for e in rec["native_args"]}
    compiler[a]=sorted([e["role"],e["target"],e["argv_sha256"]] for e in ex["events"] if e["role"] in ("rustc-full","rustc-link-only"))
    assert compiler[a]==rec["compiler_args"]
    sources[a]={"raw_native_trace_sha256":sha(raw),"original_result_sha256":sha(rec0)}
    gens[a]=rec["products"]
assert compiler["A"]==compiler["B"] and len(compiler["A"])==51 and set(events["A"])==set(events["B"])==set(matrices["A"])==set(matrices["B"])
def normalized(x,mark):
    v=x["argv"].copy()
    for kind,idx in mark["roles"].items():
        when=("-L" if x["role"]!="gcc" else "") if kind=="raw_dylibs" else "-plugin-opt=-fresolution=" if kind=="resolution" else ""
        v[idx]=when+"<"+kind+">"
    assert vector(v)==mark["stable_argv"] and vector(x["argv"])==x["argv_sha256"] and len(v)==mark["argc"]
    return v
def parse_path(x):
    q=Path(x).relative_to(root)
    prefix,marker,tail=str(q).rpartition("/")
    m=re.fullmatch(r"(.+)\.([0-9a-z]{7})\.rcgu\.o",tail)
    assert marker and m and prefix.endswith(".rlink-objects") and q.parts[0]=="target" and re.fullmatch(r"[0-9A-Za-z_./-]+",str(q))
    return q,m.group(1),m.group(2)
rows=[];operands={};touched={};sources_by_id={};report_cmp=[]
for target,role in sorted(events["A"]):
    k=target,role
    left,right=(events[a][k] for a in "AB");ra,rb=(matrices[a][k] for a in "AB")
    va,vb=normalized(left,ra),normalized(right,rb)
    assert ra["roles"]==rb["roles"] and len(va)==len(vb)
    if role=="stock-wild":assert ra["temporary_contents"]==rb["temporary_contents"]
    different=[i for i,(x,y) in enumerate(zip(va,vb)) if x!=y]
    row={"target":target,"tool":role,"argc":len(va),"normalized_sha256":[ra["stable_argv"],rb["stable_argv"]],"differing":[]}
    assert bool(different)==(ra["stable_argv"]!=rb["stable_argv"])
    if different:
        same=hashlib.sha256()
        for i,(x,y) in enumerate(zip(va,vb)):
            if x==y:same.update(i.to_bytes(4,"little")+os.fsencode(x)+b"\0")
        row["sha256_of_unchanged_indexed_normalized_tokens"]=same.hexdigest()
        for i in different:
            x,y=va[i],vb[i];ax,astem,at=parse_path(x);bx,bstem,bt=parse_path(y)
            assert ax.parent==bx.parent and astem==bstem and at!=bt and ax.parent.name==target+".rlink-objects"
            rawkey=(str(ax),str(bx))
            if rawkey not in operands:
                ind=len(operands);ls,la=filemeta("A",x);rs,lb=filemeta("B",y)
                operands[rawkey]={"index":ind,"target":target,"paths":[str(ax),str(bx)],"filename_stem":astem,"suffixes":[at,bt],"A":ls,"B":rs}
                sources_by_id[ind]=(la,lb)
            ob=operands[rawkey];row["differing"].append([i,ob["index"]])
            la,lb=sources_by_id[ob["index"]]
            ob["both_last_changes_preceded_recorded_execs"]=ob.get("both_last_changes_preceded_recorded_execs",True) and max(la.st_ctime_ns,la.st_mtime_ns)<=left["start_ns"] and max(lb.st_ctime_ns,lb.st_mtime_ns)<=right["start_ns"]
    rows.append(row)
assert len(rows)==150
for target in sorted({v["target"] for v in operands.values()}):
    a=[t for t in rows if t["target"]==target]
    groups=[tuple(i for _,i in w["differing"])for w in a]
    assert len(groups)==3 and len(set(groups))==1
    g=[v for v in operands.values() if v["target"]==target]
    receipts=[]
    for arm in "AB":
        found=[v for k,v in gens[arm].items() if Path(k).name==target];assert len(found)==1
        el=found[0];receipts.append({"sha256":el["sha256"],"bytes":el["size"]})
    touched[target]={"differing_file_pairs":len(g),"byte_identical_file_pairs":sum(v["A"]==v["B"] for v in g),
                     "relative_order_of_operands_identical_across_three_tools":True,"linked_outputs":receipts}
result={"schema":1,"source":sources,"frozen_comparator_sha256":sha(fd_bytes(comparator)[0]),"compiler_vectors_equal":compiler["A"],
    "normalized_native_vectors":rows,"objects":sorted(operands.values(),key=lambda x:x["index"]),"target_summary":touched,
    "differing_stable_vectors":sum(bool(x["differing"]) for x in rows),"control_argv_unchanged_outside_listed_positions":True,
    "payload_observation":"reopened from each held terminal view after the final trace; at-exec capture covered the compiler-owned temporary roles"}
sys.stdout.buffer.write(gzip.compress(portable(result),compresslevel=9,mtime=0))
