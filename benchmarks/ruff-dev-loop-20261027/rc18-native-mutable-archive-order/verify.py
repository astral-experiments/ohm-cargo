from pathlib import Path
import hashlib,json,re,subprocess,tarfile,tempfile
root=Path(__file__).resolve().parent;sha=lambda x:hashlib.sha256(x).hexdigest()
with tarfile.open(root/"raw.tgz")as t:data={n:t.extractfile(n).read()for n in t.getnames()};assert len(data)==len(t.getnames())==61
deny=re.compile(rb'openai[.](org|com|internal)|artifactory[.]|authorization[:][ ]bearer|github[_]pat[_]|ghp[_][A-Za-z0-9]{16}',re.I)
assert not any(deny.search(b)for b in data.values())
get=lambda key:json.loads(data[key])
dig=get("raw-digests.json");assert set(dig)==set(data)-{"raw-digests.json"} and all(sha(data[n])==v["sha256"] and len(data[n])==v["bytes"] for n,v in dig.items())
allres=get("complete.json");st=get("native-states.json");reopen=get("reopened.json");imp=get("impossible-hit.json")
want={"A0B0":41,"A1B0":97,"A1B1":97,"A0B1":83,"before-router":83,"after-selection":97,"archive-late":83}
assert set(st)=={"A0B0","A1B0","A1B1","A0B1"} and set(reopen)==set(want)==set(allres["native"])
def changed(a,b):assert len(a)==len(b);return [i for i in range(len(a))if a[i]!=b[i]]
araw,anew,braw,bnew=[data[n+".input"]for n in("A0","A1","B0","B1")]
assert changed(araw,anew)==[allres["A_raw_changed_offset"]] and changed(braw,bnew)==[allres["B_raw_changed_offset"]]
assert araw.replace(b"branch0\0",b"branch1\0")==anew and braw.replace(bytes.fromhex("b829000000c3"),bytes.fromhex("b853000000c3"))==bnew
with tempfile.TemporaryDirectory()as r:
    base=Path(r);run=lambda *a:subprocess.run(a,capture_output=True,check=True,timeout=5).stdout
    for i,b in enumerate((araw,anew)):
        p=base/f"A{i}.o";p.write_bytes(b)
        assert b"REL (Relocatable file)" in run("readelf","-hW",p)
        rel=run("readelf","-rW",p);assert b"R_X86_64_PLT32"in rel and f"branch{i}".encode()in rel and f"branch{1-i}".encode()not in rel
    for i,b in enumerate((braw,bnew)):
        p=base/f"B{i}.a";p.write_bytes(b)
        assert run("ar","t",p).splitlines()==[b"branch-zero.o",b"branch-one.o"]
        assert run("ar","p",p,"branch-one.o")==data["native/branch-one.o"]
        ob=run("ar","p",p,"branch-zero.o");assert ob==data["native/branch-zero.o"]if i==0 else changed(ob,data["native/branch-zero.o"])==[ob.index(bytes.fromhex("b853000000c3"))+1]
        assert (b"branch0 in branch-zero.o"in run("nm","--print-armap",p)) and b"branch1 in branch-one.o"in run("nm","--print-armap",p)
    for name,val in want.items():
        o=allres["native"][name];w=reopen[name];assert o==get(name+"/receipt.json") and o["status"]==w["exit"]==0 and o["value"]==val==w["value"]
        elf=base/name;elf.write_bytes(data[w["body"]]);elf.chmod(0o700)
        assert sha(elf.read_bytes())==o["elf_sha256"]==w["elf_sha256"] and int(run(elf))==val
        symbols=[l.decode()for l in run("nm","-n",elf).splitlines() if l.endswith((b" native_value",b" branch0",b" branch1"))];assert symbols==o["symbols"] and len(symbols)==2
        assert any(l.endswith("branch1" if val==97 else "branch0") for l in symbols)
        trace=data[name+"/trace"];assert sha(trace)==o["trace_sha256"]
        if name.startswith("A"):
            lines=trace.splitlines();links=[l for l in lines if b"execve("in l and b'wild-ld/ld.bfd"'in l and l.endswith(b"= 0")]
            assert len(links)==2 and links[-1].index(b"z-dispatch.o")<links[-1].index(b"a-branches.a")
            assert all(sha(lines[i])==h for i,h,_ in st[name]["native_open_lines"])
        else:
            last=trace.decode().splitlines();barrier=[i for i,l in enumerate(last) if l.startswith("barrier\topenat\t")];assert len(barrier)==1
            i=barrier[0];assert last[i+1]=="resumed" and last[-1]=="exit\t0\t1"
            assert all(ev[2:]==o["events"][0][2:]for ev in o["events"])
            if name in ("after-selection","archive-late"):
                assert last[i].endswith("/out/native_router") and all(any(l.startswith("native\t") and "\tmmap\t"in l and l.endswith(s) for l in last[:i])for s in ("a-branches.a","z-dispatch.o"))
            if name in ("before-router","after-selection"):assert [ev[:2]for ev in o["events"]]==[[49,41],[49,83],[48,83]]
            else:assert [ev[:2]for ev in o["events"]]==[[48,41],[48,83]]
            assert w["elf_sha256"]==st["A1B1"if name=="after-selection"else "A0B1"]["sha256"]
assert [x["visible_value"]for x in imp["reachable_states"]]==[97,97,83]
assert all(q[2]==imp["held_before"]==imp["held_after"]for q in imp["observer_edges"])
assert imp["fd_reads"]==[["a-branches.a",0],["a-branches.a",len(braw)],["z-dispatch.o",0],["z-dispatch.o",len(araw)]]
assert imp["batch_claim"]=={"bad":None,"status":0,"files":3,"bytes":439952} and imp["stable_end_recheck"]["status"]==11
assert imp["actual_lib"]==allres["receiver_body"]=="22235d0d6ff6113444b2876fc69e2969c42d957a6128c127ba5fb9e3e1adb29a" and imp["checked_image_sha256"]==st["A0B0"]["sha256"]
print("Verified 7 actual native Rust programs and 3 complete ELF hashes. Readelf and ar confirm one symbol-name byte and one object instruction byte, unchanged members/order/index.")
print("Stock corner results 41/97/97/83. Synchronized stock 83/97/83. Existing receiver accepts 41 through the monotone 97/97/83 states and rejects the settled end.")
