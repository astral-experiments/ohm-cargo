"""Rebuild the three-row receiver from authenticated sources and execute its actual kernel barrier."""
import argparse,hashlib,json,subprocess,tarfile
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument("--reference",type=Path,required=True,help="rc18-native-mutable-input-order packet");p.add_argument("--blake3-c",type=Path,required=True);p.add_argument("--out",type=Path,required=True);a=p.parse_args()
here=Path(__file__).resolve().parent;dest=a.out.resolve();dest.mkdir();case=dest/"case";(case/"native").mkdir(parents=True)
sha=lambda b:hashlib.sha256(b).hexdigest()
with tarfile.open(here/"raw.tgz")as tar:
    read=lambda n:tar.extractfile(n).read()
    for n in ("A0.input","A1.input","B0.input","B1.input","native-states.json","checker-barrier.py"):(dest/n).write_bytes(read(n))
    old=json.loads(read("reopened.json"))["A0B0"];gold=case/"gold";gold.write_bytes(read(old["body"]));gold.chmod(0o775)
with tarfile.open(a.reference/"raw.tgz")as tar:
    read=lambda n:tar.extractfile(n).read();build=json.loads(read("original/build2.json"));(dest/"batch2.c").write_bytes(read("original/batch2.c"))
assert sha((a.reference/"fdhash.c").read_bytes())==build["fdhash_sha"] and sha((dest/"batch2.c").read_bytes())==build["batch_sha"]
src=a.blake3_c.resolve();assert all(sha((src/k).read_bytes())==v for k,v in build["blake3"]["sources"].items());units=[str(src/k)for k in build["blake3"]["sources"] if not k.endswith(".h")]
subprocess.run(["cc","-O3","-fPIC","-shared","-Wl,-z,relro,-z,now","-pthread","-I",str(src),str(dest/"batch2.c"),str(a.reference/"fdhash.c"),*units,"-o",str(dest/"libguard2.so")],check=True)
cp=subprocess.run(["python3",str(dest/"checker-barrier.py")],capture_output=True,timeout=20)
(dest/"stdout").write_bytes(cp.stdout);(dest/"stderr").write_bytes(cp.stderr);assert cp.returncode==0,cp.stderr
v=json.loads((dest/"impossible-hit.json").read_bytes());assert v["batch_claim"]["status"]==0 and v["batch_claim"]["files"]==3 and v["stable_end_recheck"]["status"]==11
print(json.dumps({"actual_lib":v["actual_lib"],"states":v["reachable_states"],"batch_claim":v["batch_claim"],"next_status":v["stable_end_recheck"]["status"],"names_read":v["fd_reads"],"same_stat":v["held_before"]==v["held_after"]},indent=2))
