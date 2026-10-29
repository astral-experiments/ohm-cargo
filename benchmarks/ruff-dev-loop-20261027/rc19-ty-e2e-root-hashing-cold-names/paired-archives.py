"""Read the two independently verified original tar streams together, checking literal archive subjects."""
import argparse
import gzip
import hashlib
import json
import subprocess
import sys
import tarfile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
from archive import compare,sha

def get(p):return json.loads(p.read_bytes())
def file_sha(p):
    with p.open("rb") as f:return hashlib.file_digest(f,"sha256").hexdigest()
def items(archive,wanted):
    with subprocess.Popen(["zstd","-q","-dc",str(archive)],stdout=subprocess.PIPE) as extraction:
        seen=set()
        with tarfile.open(fileobj=extraction.stdout,mode="r|") as stream:
            for member in stream:
                key=Path(member.name)
                if key in wanted:
                    assert member.isfile() and not member.issym() and key not in seen,("cannot independently verify selected member",key)
                    data=stream.extractfile(member).read()
                    assert len(data)==member.size and sha(data)==wanted[key],key
                    seen.add(key);yield key,data
        extraction.stdout.close()
        assert extraction.wait()==0 and seen==wanted.keys(),(len(seen),len(wanted))

def run(k,out):
    baseline=k/"cold-archives";report=k/"reports"
    captured=[]
    for who in ("parent","child"):
        state="cold-"+who
        receipt=get(baseline/(state+".json"));archive=baseline/(state+".tar.zst")
        phase=report/state/"edited-cold";result=get(phase/"result.json")
        assert result["units"]==300 and result["fresh"]==0 and receipt["complete"]==file_sha(phase/"result.json") and receipt["archive"]==file_sha(archive)
        deps=get(phase/"dependencies.json")["typed_files"]
        # Resolve the literal target prefix from the real mount record of that exact native command.
        public=next(k for k,x in get(phase/"kernel-mounts.json")["mounts"].items() if k.endswith("/live"))
        target=Path(public)/"target"
        captured.append((archive,{Path(p).relative_to(target):x["sha256"] for p,x in deps.items() if p.endswith(".rlib")}))
    assert captured[0][1].keys()==captured[1][1].keys() and len(captured[0][1])==253
    changed={k for k,v in captured[0][1].items() if v!=captured[1][1][k]}
    gen=[items(a,{k:v for k,v in paths.items() if k in changed}) for a,paths in captured]
    out.mkdir();rows={}
    for (left,a),(right,b) in zip(*gen,strict=True):
        assert left==right and left not in rows,(left,right)
        rec=compare(a,b);assert rec["left"]==captured[0][1][left] and rec["right"]==captured[1][1][left]
        token=hashlib.sha256(str(left).encode()).hexdigest()[:20]+".json.gz"
        with (out/token).open("xb") as f:
            with gzip.GzipFile(fileobj=f,mode="wb",mtime=0,filename="") as g:g.write(json.dumps(rec,sort_keys=True,separators=(",",":")).encode())
        rows[left]={"left":rec["left"],"right":rec["right"],"result":rec["status"],"formed_exact":rec["equivalent_exact_names"],"field_count":len(rec.get("edits",[])),"record":token,"record_sha256":file_sha(out/token)}
    assert rows.keys()==changed
    summary={"all":253,"raw_equal":253-len(changed),"compared":{str(k):v for k,v in rows.items()},"all_changed_archives_accounted":all(v["formed_exact"] for v in rows.values())}
    (out/"terminal.json").write_text(json.dumps(summary,sort_keys=True,indent=2)+"\n")
if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("study",type=Path);p.add_argument("new_output",type=Path);a=p.parse_args();run(a.study,a.new_output)
