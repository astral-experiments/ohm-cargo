"""Recount every native execution and Cargo unit and compare full physical argv hashes across source directions."""
from pathlib import Path
from collections import Counter
import copy,gzip,json,re,sys
base=Path(__file__).resolve().parent
def verify(v):
 assert v["subject"]=={"old":"716260bf10d7ae1d965ed9b22653e57fbc960582","new":"2d6ce561250a464e1fa231ef30e54d0f029f76a4","lock":"34e5c62a1d7c45679fc0113e8a8814452e67d9969dd1079adb234bd7803ddc6d"}
 assert len(set(v["workspace"]))==47 and v["defaults_all"] is True
 assert set(v["series"])=={"shipped18","qualified19"}
 assert v["tools"]["shipped18"]["cargo"]=="02a86ebd2d9e4f237b33f212102b81ed145eb77fae090d67e379cb6f1d70a573"
 assert v["tools"]["qualified19"]["cargo"]=="6aaa263e68d2d77aeb8977166f9744f1fa8e0ea4df3216fe516355be68517bac"
 for n in ("rustc","stock-wild","gcc","collect2"):assert v["tools"]["shipped18"][n]==v["tools"]["qualified19"][n]
 assert v["tools"]["shipped18"]["rustc"]=="c6ab483d6698f68eebb49d74b27361f3e02ede55452dc0416c3fdec9a45b7f60"
 assert v["tools"]["shipped18"]["stock-wild"]=="0d6335808b647d499f3d74993b602e64ff0625206c809bf4913c487eea380cd5"
 for rel,series in v["series"].items():
  assert set(series)=={"unchanged-before","parent-edit","parent-unchanged-1","parent-unchanged-2","child-edit","child-unchanged-1","child-unchanged-2"}
  edit_args=[];flags=[]
  for n,d in series.items():
   assert d["source"]==v["subject"]["old" if n.startswith("parent") else "new"] and d["git_dir_unchanged"]
   assert len(d["artifacts"])==510 and all(type(u["fresh"])==bool for u in d["artifacts"])
   assert all(re.fullmatch("[0-9a-f]{64}",d[k]) for k in ("native_log_sha256","cargo_json_sha256","cargo_stderr_sha256"))
   ev=d["native"];assert all(re.fullmatch("[0-9a-f]{64}",e["argv_sha256"]) for e in ev)
   p=Counter(e["role"] for e in ev);dirty=sum(not a["fresh"] for a in d["artifacts"])
   assert p["cargo"]==1
   if n.endswith("-edit"):
    assert p=={"cargo":1,"rustc-full":51,"gcc":1,"collect2":1,"stock-wild":1} and dirty==56
    e,=[x for x in ev if x["role"]=="stock-wild"];assert re.fullmatch(r"libruff_macros-[0-9a-f]{16}\.so",e["out"])
    edit_args.append(Counter((x["target"],x["argv_sha256"]) for x in ev if x["role"]=="rustc-full"))
    assert Counter(x[2] for x in d["dirty_reasons"])=={"TargetConfigurationChanged":30,"UnitDependencyInfoChanged":26,"PrecalculatedComponentsChanged":1}
    current={a["package"]:(a["tested"],a["doctest"]) for a in d["artifacts"] if a["workspace"] and set(a["kind"])&{"lib","rlib","proc-macro"}}
    flags.append(current)
   elif n.endswith("-1"):
    native=24 if rel=="shipped18" and n=="parent-unchanged-1" else 12
    assert p=={"cargo":1,"rustc-full":native}
   else:
    assert p=={"cargo":1,"rustc-full":1} and dirty==12
  assert len(edit_args)==2 and edit_args[0]==edit_args[1] and sum(edit_args[0].values())==51
  assert len(flags)==2 and len(set(flags[0])&set(flags[1]))>=27 and sum(flags[0][k]!=flags[1][k] for k in flags[0].keys()&flags[1].keys())==27
 return True
if __name__=="__main__":
 v=json.loads(gzip.decompress((base/"observations.json.gz").read_bytes()));verify(v)
 if "--mutations" in sys.argv:
  for key in ("compiler","link","flags","source"):
   w=copy.deepcopy(v);d=w["series"]["qualified19"]["child-edit"]
   if key=="compiler":next(a for a in d["native"] if a["role"]=="rustc-full")["argv_sha256"]="0"*64
   elif key=="link":d["native"]=[a for a in d["native"] if a["role"]!="stock-wild"]
   elif key=="flags":
    for a in d["artifacts"]:
     if a["workspace"] and a["package"]=="ruff_cache":a["tested"]=not a["tested"]
   else:d["source"]=v["subject"]["old"]
   try:verify(w)
   except AssertionError:continue
   raise AssertionError("accepted "+key)
 print("Verified both 47-member workspaces, 7,140 Cargo artifact reports, four 51-compiler edits, 51/51 identical compiler argument hashes in each line, all four real links and every immediate and settled control.")
