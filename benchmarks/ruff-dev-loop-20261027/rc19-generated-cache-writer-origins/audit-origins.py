"""Bind the first four active-branch writers to their direct-parent Git blobs and PR heads."""
import argparse
import base64
import concurrent.futures
import hashlib
import json
import os
import subprocess
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument("git_checkout",type=Path)
parser.add_argument("output",type=Path)
args = parser.parse_args()
repo = args.git_checkout.resolve()
root = args.output
root.mkdir()
current = "5394ce8817e224971230b80a9066cc28d504ff94"
cases = (
    (53, "1aa523118aad2b32eb365589956a96587e527f92", "src/compiler/fingerprint/mod.rs", "paths::write_atomic(public_api_hash_path, serde_json::to_vec(&public_api_hash)?)?", "write_fingerprint_and_public_api_hash"),
    (66, "c512a35365c5de427107d7886056516b4948d46e", "src/ops/resolve_cache.rs", 'paths::write_atomic(cache_path, format!("{fingerprint:016x}"))?', "mark_workspace_resolve_fresh"),
    (75, "e42a45efcab3cf44489a071493f6d2aeafb826d2", "src/compiler/mod.rs", "paths::write_atomic(path, serde_json::to_vec(&provenance)?)?", "capture_messages(&cached_output_path)"),
    (147,"8b17025201e2e8b29b199a0dc5748dae34a73dae", "src/compiler/ohm_early_tests.rs", 'paths::write_atomic(&self.path, b"uses-library\\n")', "CheckHint"),
)
def digest(b):
    return hashlib.sha256(b).hexdigest()
def git(*a):
    return subprocess.check_output(["git","-C",str(repo),*a])
def api(endpoint):
    gh = os.environ.get("GH_AUTO",str(Path.home()/".local/bin/gh-auto"))
    return json.loads(subprocess.check_output([gh,"api","repos/astral-sh/ohm-cargo/"+endpoint],cwd=repo))
def put(name,obj):
    with (root/name).open("x") as f:
        json.dump(obj,f,indent=2,sort_keys=True)
        f.write("\n")
def fetch(c,path):
    tree=git("ls-tree",c,"--",path).decode().split()
    if not tree:
        return None,None
    assert tree[0]=="100644" and tree[1]=="blob" and tree[3]==path
    blob=tree[2]
    # Read through GitHub on every row, then match the binary Git object to the local commit tree.
    resp=api("git/blobs/"+blob)
    raw=base64.b64decode(resp["content"])
    assert resp["sha"]==blob and len(raw)==resp["size"]
    assert hashlib.sha1(b"blob "+str(len(raw)).encode()+b"\0"+raw).hexdigest()==blob
    return {"git_blob":blob,"bytes":len(raw),"sha256":digest(raw)},raw
def case(entry):
    num,rev,path,writer,marker=entry
    before=git("rev-parse",rev+"^").decode().strip()
    assert subprocess.run(["git","-C",str(repo),"merge-base","--is-ancestor",rev,current]).returncode==0
    pr=api("pulls/"+str(num))
    assert pr["state"]=="open" and not pr["draft"] and pr["head"]["sha"]==rev
    commit=api("git/commits/"+rev)
    assert [x["sha"] for x in commit["parents"]]==[before]
    before_id,old_bytes=fetch(before,path)
    after_id,new_bytes=fetch(rev,path)
    old=old_bytes.decode().splitlines() if old_bytes else []
    new=new_bytes.decode().splitlines()
    old_hits=[i+1 for i,l in enumerate(old) if writer in l]
    new_hits=[i+1 for i,l in enumerate(new) if writer in l]
    assert old_hits==[] and len(new_hits)==1 and not any(marker in l for l in old)
    idx=new_hits[0]
    bound=git("show",current+":"+path).decode().splitlines()
    curr,=[i+1 for i,l in enumerate(bound) if writer in l]
    data={"number":num,"url":pr["html_url"],"title":pr["title"],"state":pr["state"],"draft":pr["draft"],"source_branch":pr["head"]["ref"],"base_branch":pr["base"]["ref"],"base_head_when_queried":pr["base"]["sha"],"introducing_commit":rev,"direct_parent":before,"active_ancestor_of":current,"path":path,"writer":writer,"introducing_line":idx,"parent_blob":before_id,"introduced_blob":after_id,"parent_had_writer":False,"context":[{"line":j+1,"text":new[j]} for j in range(max(0,idx-6),min(len(new),idx+3))],"current_line":curr,"source_url":f"https://github.com/astral-sh/ohm-cargo/blob/{rev}/{path}#L{idx}"}
    put("pr-"+str(num)+".json",data)
    return {"pr":num,"line":idx,"current_line":curr,"sha":digest((root/("pr-"+str(num)+".json")).read_bytes())}
with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
    rows=list(pool.map(case,cases))
put("result.json",{"direct_parent_and_exact_pr_head_verified":True,"rows":rows})
print(json.dumps(rows))
