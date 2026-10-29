"""Verify genuine released Cargo, native products and mixed Rust readers."""
import collections, gzip, hashlib, itertools, json
from pathlib import Path

root = Path(__file__).resolve().parent
def digest(data): return hashlib.sha256(data).hexdigest()
def read(name):
    data = (root/name).read_bytes()
    return json.loads(gzip.decompress(data) if name.endswith(".gz") else data)
def key(data): return digest(json.dumps(data, sort_keys=True, separators=(",",":")).encode())
def require(value, label):
    if not value: raise SystemExit("Verification failed: " + label)
sigs=dict(line.strip().split("  ")[::-1] for line in (root/"SHA256SUMS").read_text().splitlines())
require(set(sigs)=={f.name for f in root.iterdir() if f.is_file() and f.name!="SHA256SUMS"}, "all files present")
for f,h in sigs.items():require(digest((root/f).read_bytes())==h,f)
q=read("qualification.json");c=read("commands.json.gz");events=read("physical.json.gz");rs=read("typed-rosters.json.gz");le=read("literal-products.json.gz");raw=read("raw-ledger.json.gz")
assert set(c)==set(events)==set(raw) and q["strict_output_identity"]=="failed" and q["scored_visits"]==0
assert q["release_cargo"]=={"A":"3a94265b0d3c80afd228f575190a8c291506951b1a77e45bb9bac2aa89387df7","B":"51eb6c59a38151fbf1a252d7bc39cb45dfa67482a95b526e1301046bbf593ce9"}
for label,v in c.items():
    assert v["native_sha256"]==raw[label]["native.json"] and len(rs[v["roster_sha"]])==v["unit_count"]
    assert v["physical_counts"]==dict(collections.Counter(e["role"] for e in events[label]))
    assert len([e for e in events[label] if e["role"]=="cargo"])==1
    assert v["tools"]["rustc"]==q["stock_rust"] and v["tools"]["stock-wild"]=="0d6335808b647d499f3d74993b602e64ff0625206c809bf4913c487eea380cd5"
for kh,mp in le.items():assert len(mp)==597 and key(mp)==kh
allowed={"libruff_linter-b6d3cd0bff22fbfa.rmeta","libruff_source_file-e58055ef29b03e8c.rlib","libruff_python_trivia-93ff9c45c823e6e1.rlib","libruff_text_size-48bf6883a673a9b0.rlib"}
comb=read("all-pair-comparisons.json.gz");assert len(comb)==48
versions=set();linter_args=set()
for direction in ("child-to-parent","parent-to-child"):
    ids=("A","A2","B","B2")
    for k in ids:
        case=direction+"-"+k;t=q["native"][case]
        assert all(t["linter"][s]["physical_body"] for s in ("before","repeat1","repeat2"))
        cred=t["linter"]["repeat2"]["credentials"];versions.add(cred[0]);assert cred[1:]==["11340730689575692863","e80292fb4eb85b137360e3f0c75d6d62"]
        for stage in ("before","edit","repeat1","repeat2"):
            name=case+"/"+stage;v=c[name];real=events[name]
            assert v["unit_count"]==510 and v["exit"]==0 and v["tools"]["cargo"]==q["release_cargo"][k[0]] and all(e["exit"]==0 for e in real)
            assert v["git_admin"]["equal"] and v["git_admin"]["before_sha256"]==v["git_admin"]["after_sha256"] and not v["git_admin"]["training"]
            assert v['physical_counts'].get("stock-wild",0)==int(stage=="edit")
            assert [x["crate"] for x in real if x["role"]=="rustc-full"]==t["full_compiles"][stage] and v['all_597_products']==t["input_output_ledger"][stage]
            if stage=="edit":
                linter_args.update(e["argv_sha256"] for e in real if e["crate"]=="ruff_linter" and e["role"]=="rustc-full")
            if stage in ("before","repeat2"):assert t["full_compiles"][stage]==["ty_python_semantic"]
    for k,l in itertools.combinations(ids,2):
        for st in ("before","edit","repeat1","repeat2"):
            lhs,rhs=[c[direction+"-"+i+"/"+st] for i in (k,l)]
            assert lhs["roster_sha"]==rhs["roster_sha"]
            a,b=[le[i["all_597_products"]] for i in (lhs,rhs)];assert a.keys()==b.keys()
            actual={Path(s).name for s in a if a[s]!=b[s]}
            spec=comb[direction+":"+k+"/"+l+":"+st]
            assert actual==set(spec)==(set() if st=="before" else allowed)
            for nm,v in spec.items():
                z=v.get("analysis")
                if z is None:
                    assert st=="edit" and nm.endswith(".rmeta") and not all(v["bodies_available"]);continue
                assert z["sizes"][0]==z["sizes"][1] and z["changed_dep_rows"]==[[],[]]
                if nm.endswith(".rmeta"):
                    p=z["private_svh_field"];assert p["entire_reconstructed"] and p["reconstructed_sha256"]==v["hashes"][1] and p["offset"]==12165345
                    assert p["prefix_sha256"][0]==p["prefix_sha256"][1] and p["suffix_sha256"][0]==p["suffix_sha256"][1]
                else:
                    ar=z["archive"];t=ar["literal_nonce"];assert t["entire_reconstructed"] and t['reconstruction_sha256']==v["hashes"][1]
                    assert ar["native_payloads_same"] and t["old_occurrences"]==t["new_occurrences"]==2*ar["changed_member_names"] and len(t["old"])==len(t["new"])==7
                    assert ar["regular_payload_changed"][0][:2]==["lib.rmeta-link","lib.rmeta-link"] and len(ar["regular_payload_changed"])==1
assert len(versions)==8 and linter_args=={"dd9e54f92428df16ee74f182ed797a7daa2d4ee1a300578be50b42766794d94c"}
readers=read("readers.json.gz");assert len(readers)==40
total=collections.Counter()
for tag,row in readers.items():
    assert row['current_linter']==q["native"][row["current"]]["linter"]["repeat2"]["raw"]
    pr=row['programs'];v=q["native"][row["previous"]]["linter"]["repeat2"]["credentials"]
    if row["mode"]=="train":
        assert pr['bad']['codes']==['E0609'] and pr['bad']['status']==1 and pr['natural']['status']==pr['edge']['status']==row['intermediate_build']['status']==0
        for n,expected in (('intermediate',v[0]),('ruff_graph',v[2]),('ruff_workspace',v[2])):
            assert " hash "+expected+" " in row['headers'][n]['linter_rows'][0]
        total["bad"]+=1
    else:
        same=row['previous']==row['current']
        for n in ('natural','edge'):
            a,b=pr[n]['warm'],pr[n]['empty'];ok=(n=='natural' or same)
            assert a['codes']==b['codes']==([] if ok else ["E0460"])
            assert a['status']==b['status']==(0 if ok else 1) and a['stderr']==b['stderr'] and a['output']==b['output'] and a['raw_argv_sha']==b['raw_argv_sha']
            total[(n,ok)]+=2
assert total=={"bad":8,('natural',True):64,('edge',True):16,('edge',False):48}
runtime=read("native-runtime.json");assert len(runtime)==8 and len({v['full_elf'] for v in runtime.values()})==1
for k,v in runtime.items():
    assert v['exit']==v['compiler_exit']==0 and v['stdout']=="2 2 false 5\n" and v["source"]==digest((root/"native.rs").read_bytes())
    assert {f[0] for f in v['inputs'].values()}=={n for n in allowed if n.endswith('.rlib')}
    assert [e[1] for e in v['actual_executions']]==['rustc','rustc','cc','collect2','ld.lld','rust-lld']
for k in ("A","B","empty-B"):
    e=c[f"errors-{k}/selected-error"];w=c[f"errors-{k}/workspace-error"]
    assert e['error_codes']==w['error_codes']==['E0624'] and e['exit']==w['exit']==101 and e['diagnostic_sha256']==q['checked_incompatible_diagnostics'][k]
    assert any(s['is_primary'] and s['file_name'].endswith('ruff_python_index/src/multiline_ranges.rs') and s['line_start']==50 for s in e['diagnostics'][0]['spans'])
    assert c[f"errors-{k}/workspace-restored"]['exit']==c[f"errors-{k}/selected-restored"]['exit']==0
assert len(set(q['checked_incompatible_diagnostics'].values()))==1
for k in "AB":
    for s in ("edit","repeat","restore","restore-repeat"):
        assert sorted(e['crate'] for e in events[f'holdout-{k}/{s}'] if e['role']=='rustc-full')==(["ruff_python_index","ty_python_semantic"] if s in ("edit","restore") else ["ty_python_semantic"])
assert len(read("objects.json.gz")["never_observed"])==3
assert len(read("cold-native-probes.json")["probes"])==45
print(f"Verified {len(c)} genuine Cargo calls, 32 historical workspace commands across eight resets, 597 exact shared inputs per direction, eight distinct private SVHs, 128 warm/empty Rust reader results, eight identical runnable ELFs, and zero scored pairs.")
