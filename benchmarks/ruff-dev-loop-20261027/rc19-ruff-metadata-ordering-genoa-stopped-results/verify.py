"""Verify the stopped Genoa cohort and keep the incomplete third pair distinct."""
from pathlib import Path
import ast, gzip, hashlib, json
p=Path(__file__).resolve().parent
digest=lambda b:hashlib.sha256(b).hexdigest()
def read(n):
 b=(p/n).read_bytes();return json.loads(gzip.decompress(b) if n.endswith('.gz') else b)
def key(d):return digest(json.dumps(d,sort_keys=True,separators=(",",":")).encode())
m={s.split("  ",1)[1]:s.split("  ",1)[0] for s in (p/"SHA256SUMS").read_text().splitlines()}
assert set(m)=={f.name for f in p.iterdir() if f.is_file() and f.name!="SHA256SUMS"} and all(digest((p/k).read_bytes())==v for k,v in m.items())
t=read("stopped.json");o=read("order.json");a=read("ordinary-commands.json");c=read("closed-readers.json.gz");ll=read("closed-raw-products.json.gz");rosters=read("typed-rosters.json.gz");checkpoints=read("held-checkpoints.json");raw=read("per-visit-source-ledger.json");foot=read("after-stop-archive.json.gz")
assert m["order.json"]==t["fixed_order_sha"]=="b7594ea85252780260b1aecce5221a548adcd4b4cce8c8353f77321a4f9c3093"
assert t['original_protocol']=="5ef08a85860887a0eb92c12bf51174a6264ab806989f807e2fb9c2f78bfb274e" and t['native_manifest']=="ed552d17bd94cc464d4eea6addaa2427225cd3ddd8ef2caba9dfe805ab250b6d" and t['supplement_manifest']=="05f901037ede7e79a91dfbf81651a2a41d7b2cb8d3b410a2cedf57463b8fdba3"
assert t['status']==1 and t['completed_pairs']==2 and t['unattempted_pairs']==29 and not t['product_effect_estimated'] and len(o)==t['expected_pairs']==32
assert len(a)==t['timed_visits']==6 and {v['case'] for v in a}==set(checkpoints)==set(raw) and len(c)==len(ll)==4
assert t['stop_floor']['volume']==1047527424 and t['floor_min']['volume']==1073741824 and t['floor_min']['volume']-t['stop_floor']['volume']==t['shortfall']==25*1024*1024
assert all(t['stop_floor'][k]>t['floor_min'][k] for k in ('home','scratch')) and t['failed_pair']==2
rn={"libruff_linter-b6d3cd0bff22fbfa.rmeta","libruff_source_file-e58055ef29b03e8c.rlib","libruff_python_trivia-93ff9c45c823e6e1.rlib","libruff_text_size-48bf6883a673a9b0.rlib"}
s0,s1="716260bf10d7ae1d965ed9b22653e57fbc960582","2d6ce561250a464e1fa231ef30e54d0f029f76a4"
series=0
for j,v in enumerate(a):
 n,slot=divmod(j,2);arm=o[n]['order'][slot];case=f"pair-{n:02d}-visit-{slot}-{arm}";assert v['case']==case and v['pair']==n and v['arm']==arm and v['direction']==o[n]["direction"] and v['order']==o[n]["order"]
 assert v['sources']==([s0,s1] if v['direction']=="parent-to-child" else [s1,s0]) and v['cpus']==list(range(8))
 assert v['real_cargo']==({'A':"3a94265b0d3c80afd228f575190a8c291506951b1a77e45bb9bac2aa89387df7",'B':"51eb6c59a38151fbf1a252d7bc39cb45dfa67482a95b526e1301046bbf593ce9"}[arm])
 assert v['closed_pair']==(n<2) and v['git_control_after']==[v['git_control_before']]*2
 assert {k:i['sha256'] for k,i in v['metadata'].items()}=={"libruff_python_ast-98ec24b9d64d5496.rmeta":"08616e086102c8430390df283e17e7b7c33f55551490d71f2988d69a0186e007","libruff_python_index-26cfa97e490770a3.rmeta":"625153260f531179114c3b2c69c1dec87ab581a2948099c55a2b0b05beb41158"}
 for k,w in zip(("edit","repeat"),v["stopwatches"],strict=True):
  q=v['status'][k];assert q['units']==510 and q['returncode']==w['status']==0 and w['step']==k and w['to_ns']-w['from_ns']==w['elapsed_ns']>0
  assert len(rosters[q['typed_roster']])==510 and key(rosters[q['typed_roster']])==q['typed_roster'] and raw[case][k+'.jsonl']==q['raw_stdout']
  series+=1
 assert checkpoints[case]['terminal_sha256']==raw[case]['terminal.json'] and checkpoints[case]['checkpoint_sha256']==raw[case]['checkpoint.json']
 if n<2:
  f=ll[case];w=c[case]
  assert len(f)==597 and key(f)==w['all_products_digest'] and len(w['source_files'])==30 and w["calls"]["valid"]['status']==w["calls"]["recovered"]['status']==0
  assert w["calls"]["invalid"]['codes']==['E0609'] and w["calls"]["invalid"]['status']==1 and w["calls"]["recovered"]["output"]==w["calls"]["valid"]["output"]
  assert set(w['four_raw_files'])==rn and all(any(Path(n).name==k and v==z['actual'] for n,v in f.items()) for k,z in w['four_raw_files'].items())
 else:
  assert case not in c and case not in ll
  x=foot[case];assert x['after_stop_archival_only'] and not x['reader_run'] and not x['cargo_run'] and x['official_validation'] is None
  assert x['raw_checkpoint']==checkpoints[case]['checkpoint_sha256'] and len(x['outputs'])==597 and set(x['native_files'])==rn and len(x['source_files'])==30
  assert all(any(Path(n).name==k and v['sha256']==h for n,v in x['outputs'].items()) for k,h in x['native_files'].items())
assert series==12 and set(c).isdisjoint(foot) and len(foot)==2 and not (p/'analysis.json').exists()
archive=read("archive-custody.json")
assert archive["original_stop_stderr"]==t["raw_stderr"] and m["first-stop.txt"]==t["raw_stop"]
assert (p/"first-stop.txt").read_text().strip()=="pair=2 visit=0 stage=post-pair exit=1"
threshold_error=(p/"floor-receipt.txt").read_text().strip().splitlines()[-1]
assert threshold_error.startswith("AssertionError: ")
floors=ast.literal_eval(threshold_error.split(": ",1)[1])
assert floors=={f"<{k}>":v for k,v in t["stop_floor"].items()}
assert archive["recovered_reports"]=={case:row["original_report_sha256"] for case,row in foot.items()}
for direction in {v["direction"] for v in a}:
 assert len({v["input_ledger"] for v in a if v["direction"]==direction})==1
print("Verified six actual visits and twelve ordinary 510-unit Cargo checks, four completed reader/product gates, two incomplete visits, 25 MiB floor failure and zero eligible host series.")
