"""Verify preserved raw calls, path ordering, full-ELF and permission facts; run every native body."""
from pathlib import Path
import gzip,hashlib,json,os,re,subprocess,sys,tarfile,tempfile
p=Path(__file__).resolve().parent
sha=lambda b:hashlib.sha256(b).hexdigest()
deny=re.compile(bytes.fromhex("6f70656e61695b2e5d286f72677c636f6d7c696e7465726e616c297c61727469666163746f72795b2e5d7c617574686f72697a6174696f6e3a206265617265727c6769746875625f7061745f7c6768705f5b412d5a612d7a302d395d7b31367d"),re.I)
with tarfile.open(p/'raw.tgz')as t:
    data={n:t.extractfile(n).read()for n in t.getnames()};assert len(data)==len(t.getnames())==58
assert all(not deny.search(v)for v in data.values())
get=lambda n:json.loads(data[n])
refs=get("original-sha256.json");assert len(refs)==52
for name,val in refs.items():assert sha(data[name])==val["sha256"] and len(data[name])==val["bytes"] and val["stored"]==name
stable=get("original/native-states.json");dynamic=get("synchronized/synchronized.json");claim=get("original/impossible-hit.json");repeat=get("reopened.json")
assert sha(data["original/native-states.json"])==dynamic["original_native_sha256"] and sha(data["original/impossible-hit.json"])==dynamic["impossible_claim_sha256"]
assert dynamic["subjects"]["stock_wild"]=="0d6335808b647d499f3d74993b602e64ff0625206c809bf4913c487eea380cd5"
want={"A0B0":41,"A1B0":97,"A1B1":97,"A0B1":83}
with tempfile.TemporaryDirectory() as d:
    for n,r in repeat.items():
        b=data[r["body"]];assert sha(b)==r["sha256"] and len(b)==r["bytes"] and not r["private_string_in_original_elf"]
        f=Path(d)/n;f.write_bytes(b);f.chmod(0o700)
        cp=subprocess.run([f],capture_output=True,timeout=4);assert cp.returncode==r["exit"]==0 and cp.stdout.decode()==r["stdout"] and cp.stderr.decode()==r["stderr"]==""
        assert int(cp.stdout)==r["expected"]
assert len(repeat)==8
for name,val in want.items():
    r=stable[name];assert r["runtime"]==val==repeat[name]["expected"] and r["sha256"]==repeat[name]["sha256"]
    assert r["wild_count"]==2 and r["wild"]==dynamic["subjects"]["stock_wild"] and r["rustc_driver"]==dynamic["subjects"]["candidate_driver"]
    assert r["cargo"][1:]==["+ohm","build","--locked","--offline","-j1","--message-format=json"]
    lines=data[f"original/{name}/trace"].splitlines()
    wild=[l for l in lines if b"execve("in l and b'wild-ld/ld.bfd"'in l and l.endswith(b"= 0")]
    assert len(wild)==2 and sha(wild[-1])==r["true_native_exec_line"]
    expected=r["body0_opens"] if name[1]=="0" else r["alternate_opens"]
    absent=r["alternate_opens"] if name[1]=="0" else r["body0_opens"]
    assert not absent and r["router_opens"][0][0]<expected[0][0]
    for fact in r["router_opens"]+expected:
        line=lines[fact[0]];assert sha(line)==fact[1] and b"openat" in line and re.search(rb'= [0-9]+$',line)
assert [v["visible_value"] for v in claim["reachable_states"]]==[97,97,83]
assert [e[0]for e in claim["observer_edges"]]==["A1B0","A1B1","A0B1"]
assert [e[1]for e in claim["observer_edges"]]==[[49,48],[49,49],[48,49]]
assert all(e[2]==claim["held_before"]==claim["held_after"] for e in claim["observer_edges"])
assert claim["fd_reads"]==[["a0.so",0],["a0.so",127],["z-router.so",0],["z-router.so",123]]
assert len(claim["rows"])==7 and claim["batch_claim"]=={"status":0,"files":7,"bytes":441641,"bad":None}
assert claim["stable_end_recheck"]["status"]==11 and claim["checked_image_sha256"]==repeat["A0B0"]["sha256"]
bp=get("original/build2.json");assert bp["batch_sha"]==sha(data["original/batch2.c"]) and bp["libguard"]==claim["actual_lib"] and bp["fdhash_sha"]==sha((p/"fdhash.c").read_bytes())
for n,r in dynamic["rows"].items():
    assert r==get(f"synchronized/{n}/receipt.json") and r["elf_sha256"]==repeat[n]["sha256"] and r["value"]==repeat[n]["expected"]
    assert not r["watched_host_write_fds"] and all(k=={"accepted":False,"errno":"EAGAIN"}for k in r["read_leases_while_mapped"])
    assert len(r["read_leases_while_mapped"])==len(r["read_leases_after_unmap"]) and all(k=={"accepted":True} for k in r["read_leases_after_unmap"])
    logs=data[f"synchronized/{n}/kernel.tsv"];assert sha(logs)==r["kernel_tsv_sha256"] and logs.endswith(b"exit\t0\t1\n")
    raw=logs.decode().splitlines();assert [l for l in raw if l.startswith("native\t")]==r["native_events"]
    assert [l for l in raw if l.startswith("exec\t")]==r["exec_lines"]
    ctl=raw.index("barrier\topenat\t"+r["native_trigger"]);assert raw[ctl+1]=="resumed"
    seq=[Path(l.split("\t")[2]).name for l in r["exec_lines"]];assert seq.count("collect2")==2 and seq.count("ld.bfd")==2 and seq.count("x86_64-linux-gnu-gcc-13")==2
    assert all(k["stamps"]==r["events"][0]["stamps"]for k in r["events"])
    if n.endswith("router"):
        assert [x["state"] for x in r["events"]]==["A1B0","A1B1","A0B1"]
        equiv="A0B1" if n=="before-router" else "A1B1"
        assert r["elf_sha256"]==stable[equiv]["sha256"]
        used=[Path(l.split("\t")[-1]).name for l in r["native_events"] if "\topenat\t" in l]
        assert used[:3]==(["z-router.so","a0.so","value-1.o"] if n=="before-router" else ["z-router.so","a1.so","value-2.o"])
    else:
        assert [x["byte_values"][0]for x in r["events"]]==[41,83]and r["value"]==83
        if n=="after-object":assert any("\tmmap\t"in l and l.endswith("/value-0.o") for l in raw[:ctl]) and r["native_trigger"].endswith("/out/native_router")
print("Verified 4 independent cold corners and 4 synchronized full Cargo programs; reran 8 ELF bodies.")
print("Receiver accepted 41; reachable corners give 97, 97, 83; actual stock barriers gave 83 and 97.")
print("Both direct-object barriers gave 83. Six read leases refused existing writable mappings, six succeeded after their removal.")
