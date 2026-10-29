"""Reclaim exactly two verified, owned read-only snapshots on the study loop mount."""
import json, os, re, stat, subprocess, sys
from pathlib import Path
def field(output, key):
    m=re.search(r"^\s*"+key+r":\s*(\S+)\s*$",output,re.M);assert m;return m[1]
def main():
    r,volume=map(Path,sys.argv[1:3]);uid=int(sys.argv[3]);mode=sys.argv[4]
    assert os.geteuid()==0 and uid==1000 and volume.is_absolute() and volume.resolve()==volume
    assert r.is_absolute() and Path(__file__).resolve().parent.parent==r and r.stat().st_uid==uid
    mount=subprocess.check_output(["findmnt","-n","-o","TARGET,FSTYPE","--target",volume],text=True).split()
    assert mount==[str(volume),"btrfs"]
    if mode=="demo":
        valid=r/"genoa-supplement-custody-demo-pre.json"
        names={"supplement-demo-v2-held-"+a for a in "AB"}
    else:
        n=int(sys.argv[5]);assert mode=="score" and 0<=n<32
        schedule=json.loads((r/"protocol-v1/genoa.json").read_bytes());assert schedule[n]['pair']==n
        names={f"supplement-held-pair-{n:02d}-visit-{i}-{k}" for i,k in enumerate(schedule[n]["order"])}
        valid=r/"genoa-supplement-scored"/f"pair-{n:02d}.validated.json"
    assert valid.is_file() and not valid.is_symlink() and valid.stat().st_uid==uid
    v=json.loads(valid.read_bytes());assert v["uid"]==uid and set(v["owned"])==names and len(names)==2
    deletion=[]
    for name in sorted(names):
        p=volume/name
        assert p.parent==volume and p.resolve()==p and stat.S_ISDIR(p.lstat().st_mode) and p.stat().st_uid==uid
        assert subprocess.check_output(["btrfs","property","get","-ts",p,"ro"],text=True).strip()=="ro=true"
        live=subprocess.check_output(["btrfs","subvolume","show",p],text=True)
        assert all(field(live,k)==field(v["owned"][name],k) for k in ("Subvolume ID","UUID","Parent UUID"))
        deletion.append(p)
    for p in deletion:subprocess.run(["btrfs","subvolume","delete","--commit-after",p],check=True)
    assert all(not p.exists() for p in deletion)
if __name__=="__main__":main()
