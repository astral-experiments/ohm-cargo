"""Identify true cold inputs separately; do not share credentials with other histories."""
import gzip
import re
import subprocess
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parent))
from common import *

# Only the exact known Rust object form in the GNU table and Rust's metadata stub
# may contain an independently spelled generated object name. Leave real payloads alone.
OBJ=re.compile(rb'([a-zA-Z_][a-zA-Z0-9_]*-[a-f0-9]{16}\.[a-z0-9]+)\.([0-9a-z]{7})\.rcgu\.o')

def ar_signature(path):
    blob=path.read_bytes()
    assert blob.startswith(b"!<arch>\n"),path
    at=8;table=b"";members=[];allowed=[];names=set();seen={}
    while at<len(blob):
        header=blob[at:at+60];assert len(header)==60 and header[-2:]==b"`\n",path
        short=header[:16].rstrip();count=int(header[48:58]);start=at+60;body=blob[start:start+count]
        assert len(body)==count
        if re.fullmatch(rb"/\d+",short):
            pos=int(short[1:]);assert pos==0 or table[pos-2:pos]==b"/\n"
            literal=table[pos:table.index(b"/\n",pos)]
        else:
            literal=short if short in (b"/",b"//") else short.removesuffix(b"/")
        if literal==b"//":
            table=body
        matches=[]
        if literal in (b"//",b"lib.rmeta-link"):
            for v in OBJ.finditer(body):
                matches.append(v[0]);allowed.append((start+v.start(2),v[2]))
            seen[literal]=matches
        if OBJ.fullmatch(literal):
            assert literal not in names
            names.add(literal)
        members.append([literal.decode(),count,hashlib.sha256(body).hexdigest(),at,hashlib.sha256(header).hexdigest()])
        at=start+count+(count%2)
    assert at==len(blob)
    # A set is accepted only when all changed seven-byte fields are names of actual members.
    usable=bool(names) and set(seen.get(b"//",[]))==names and all(set(ms)<=names for ms in seen.values())
    if any(names):
        usable=usable and len({OBJ.fullmatch(n)[2] for n in names})==1
    out=bytearray(blob)
    if usable:
        for i,b in allowed:
            assert out[i:i+7]==b
            out[i:i+7]=b"NoncE00"
    return {"literal":hashlib.sha256(blob).hexdigest(),"only_observed_names_masked":hashlib.sha256(out).hexdigest(),
            "accepted_name_field_count":len(allowed) if usable else 0,"members":members}

def diagnostics(d,closure,env):
    decoded={};archives={};q=d/"decoded";q.mkdir()
    for item,props in closure["typed_files"].items():
        p=Path(item)
        if p.suffix==".rlib":
            archives[item]=ar_signature(p)
        if p.suffix!=".rmeta":
            continue
        key=hashlib.sha256(os.fsencode(p)).hexdigest()[:18]
        rr=subprocess.run(["rustc","+ohm","-Zls=root",str(p)],env=env,cwd=ROOT,capture_output=True,timeout=20)
        (q/(key+".stdout")).write_bytes(rr.stdout);(q/(key+".stderr")).write_bytes(rr.stderr)
        assert rr.returncode==0 and rr.stdout.startswith(b"Crate info:"),(p,rr.returncode,rr.stdout[:80],rr.stderr[:80])
        head=rr.stdout.splitlines()
        identity=next(x for x in head if x.startswith(b"private hash "))
        public=next((x for x in head if x.startswith(b"public_hash ")),None)
        decoded[item]={"raw":props["sha256"],"private_hash_and_stable_id":identity.decode(),"public_hash":public.decode() if public else None,
                       "full_decoder_stdout":hashlib.sha256(rr.stdout).hexdigest(),"prefix":key}
    assert len(decoded)==len(archives)==253
    with (d/"whole-dependency-diagnostics.json.gz").open("xb") as sink:
        with gzip.GzipFile(fileobj=sink,mode="wb",filename="",mtime=0) as gz:
            gz.write(json.dumps({"metadata":decoded,"archives":archives},sort_keys=True,separators=(",",":")).encode())

def escrow(lane):
    assert lane in ("cold-parent","cold-child") and os.getuid()==1000
    work=LANES/lane;target=work/"empty-target";receipt=REPORTS/lane/"edited-cold/result.json"
    assert get(receipt)["fresh"]==0 and target.is_dir() and not target.is_symlink() and not os.path.ismount(target)
    assert K in target.parents and LANES in target.parents
    assert (target/"debug").is_dir() and not (target/".git").exists()
    d=K/"cold-archives";d.mkdir(exist_ok=True)
    out=d/(lane+".tar.zst")
    assert not out.exists()
    before=floors(900_000_000)
    p=subprocess.Popen(["tar","--create","--format=posix","--sort=name","--sparse","--numeric-owner","--xattrs","--acls","-I","zstd -q -3 -T1","-f",out,"-C",target,"."])
    import time
    low=before.copy()
    while p.poll() is None:
        now=free();low={k:min(low[k],v)for k,v in now.items()}
        if any(now[k]<SCHEMA[k+"_floor"] for k in now):
            p.terminate()
            break
        time.sleep(.3)
    assert p.wait()==0 and all(low[k]>=SCHEMA[k+"_floor"] for k in low),low
    verify=prior.module("cold_tree",M/"cold_escrow.py").verify
    actual=verify(target,out)
    put(d/(lane+".json"),{"archive":rawsha(out),"archive_bytes":out.stat().st_size,"verified":actual,"min_free":low,"complete":rawsha(receipt),"native_evidence":rawsha(REPORTS/lane/"edited-cold/native.json")})
    # Only this newly allocated one-shot target is recoverably released; previous study stores are untouched.
    assert rawsha(out)==get(d/(lane+".json"))["archive"] and (target/"debug").is_dir()
    shutil.rmtree(target)
