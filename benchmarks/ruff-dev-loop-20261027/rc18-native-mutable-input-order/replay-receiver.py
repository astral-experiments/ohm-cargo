"""Replay the actual receiver's cross-file false hit in a new private directory on x86-64 Linux."""
from pathlib import Path
import argparse,hashlib,json,os,subprocess,tarfile,tempfile
p=Path(__file__).resolve().parent
q=argparse.ArgumentParser()
q.add_argument("--blake3-c",type=Path,required=True,help="c subdirectory of the blake3 1.8.5 crate")
q.add_argument("--out",type=Path,required=True,help="new private directory for the replay and receipt")
args=q.parse_args();dest=args.out.resolve();dest.mkdir();source=args.blake3_c.resolve()
hashbytes=lambda b:hashlib.sha256(b).hexdigest()
with tarfile.open(p/"raw.tgz")as t:
    read=lambda k:t.extractfile(k).read()
    source_bytes=read("original/opposite-order.py")
    original=source_bytes.decode()
    build=json.loads(read("original/build2.json"));states=json.loads(read("original/native-states.json"));receipt=json.loads(read("reopened.json"))
    (dest/"batch2.c").write_bytes(read("original/batch2.c"));(dest/"gold-original").write_bytes(read(receipt["A0B0"]["body"]))
    (dest/"refs.json").write_bytes(read("original/native-states.json"))
    assert hashbytes((dest/"gold-original").read_bytes())==states["A0B0"]["sha256"]
    for i in range(3):(dest/f"prebuilt-{i}.o").write_bytes(read(f"native/value-{i}.o"))
assert all(hashbytes((source/k).read_bytes())==v for k,v in build["blake3"]["sources"].items())
assert hashbytes((p/"fdhash.c").read_bytes())==build["fdhash_sha"] and hashbytes((dest/"batch2.c").read_bytes())==build["batch_sha"]
units=[str(source/k)for k in build["blake3"]["sources"] if not k.endswith(".h")]
subprocess.run(["cc","-O3","-fPIC","-shared","-Wl,-z,relro,-z,now","-pthread","-I",str(source),str(dest/"batch2.c"),str(p/"fdhash.c"),*units,"-o",str(dest/"libguard2.so")],check=True)
declarations,rest=original.split("for dest,value in zip(payload,(41,83,97)):",1)
scripts=rest[rest.index("def script(dest):"):rest.index('src=work/"workspace"')]
acquire=original[original.index("router.write_bytes(a0);old_body.write_bytes(b0)\n# The unchanging inputs"):]
fixture="""for i,path in enumerate(payload): shutil.copyfile(root/f"prebuilt-{i}.o",path)
refs=json.loads((root/"refs.json").read_bytes());image=work/"gold";shutil.copyfile(root/"gold-original",image);image.chmod(0o775)
"""
(dest/"reader.py").write_text(declarations+scripts+fixture+acquire)
cp=subprocess.run(["python3",str(dest/"reader.py")],capture_output=True,timeout=20)
(dest/"stdout").write_bytes(cp.stdout);(dest/"stderr").write_bytes(cp.stderr)
assert cp.returncode==0,cp.stderr
out=json.loads((dest/"impossible-hit.json").read_bytes());assert out["batch_claim"]["status"]==0 and out["batch_claim"]["files"]==7 and out["stable_end_recheck"]["status"]==11
print("Receiver replay accepted the prior 41 through all seven records. Stable end recheck declined.")
