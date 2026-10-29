"""Verify the receiver's full success/failure decisions, intermediate bytes and observed worker ordering."""
import gzip,hashlib,json,re
from pathlib import Path
root=Path(__file__).resolve().parent
dig=lambda b:hashlib.sha256(b).hexdigest()
if (root/'SHA256SUMS').exists():
    for text in (root/'SHA256SUMS').read_text().splitlines():
        h,p=text.split("  ",1);assert dig((root/p).read_bytes())==h,p
data=json.loads(gzip.decompress((root/"native.json.gz").read_bytes()))
identity=json.loads((root/"identity.json").read_bytes());arm=identity["arm"]
assert identity["stock_rust"]=="a4fa11bcd38280639cb94daacc125472657db6c3"
assert identity["tools"]["rustc"]=="c6ab483d6698f68eebb49d74b27361f3e02ede55452dc0416c3fdec9a45b7f60"
assert identity["tools"]["librustc_driver-b03bf00bec23bb9a.so"]=="a7648053cbad025c1bb0bebb7009ce9e1515bdb02e8c30bef29b52a881e5b8de"
def names(row):return [x["crate"] for x in row["compiler_execs"]]
def api(rows,warm,cold,error):
    x,y=rows[warm],rows[cold]
    assert x["status"]==y["status"]==101 and x["diagnostics"]==y["diagnostics"]
    assert any(m['code']==error for m in x["diagnostics"])
def check_order(group,prefix):
    rows={}
    for mode in ("provider-first","provider-late"):
        name=prefix+mode;r=group[name]
        for n in ("provider","reader"):
            assert len([e for e in r['compiler_execs'] if e['crate']==n])==1
        assert r['status']==0,r
        assert r['before']['provider']['sha256']==r['after']['provider']['sha256']
        order=r['ordering']
        assert all('timeout' not in s['event'] and 'error' not in s['event'] for s in order)
        hold=next(i for i,s in enumerate(order) if s['event']=='hold-fd')
        release=next(i for i,s in enumerate(order) if s['event']=='release-fd')
        assert order[hold]['role']==order[release]['role']==('provider' if mode=='provider-late' else 'reader')
        if mode=='provider-late':
            assert any(hold<i<release and x["role"]=='reader' and x['event']=='after-fd' for i,x in enumerate(order))
        else:
            assert any(i<release and x['role']=='provider' and x['event']=='after-fd' for i,x in enumerate(order))
        r1,r2=group[name+"-first-repeat"],group[name+"-second-repeat"]
        if mode=='provider-late' and arm=='parent':
            assert names(r1)==['reader'] and r['after']['provider']['mtime_ns']>r['after']['reader']['mtime_ns']
            assert any('dependency on \x60provider\x60 is newer' in l for l in r1['cargo_notes'])
        else:
            assert names(r1)==[] and r['after']['provider']['mtime_ns']<=r['after']['reader']['mtime_ns']
        assert names(r2)==[] and r1['status']==r2['status']==0
        for repeat in (r1,r2):
            for n in ('provider','reader'):
                assert r['after'][n]['sha256']==repeat['after'][n]['sha256']
        rows[mode]=r
    for f in ('sources',):
        assert rows['provider-first'][f]==rows['provider-late'][f]
    for k in ('provider','reader'):
        normal,late=rows['provider-first'],rows['provider-late']
        for name in ('before','after'):
            assert normal[name][k]['sha256']==late[name][k]['sha256']
        argv=lambda row: next(e['original_argv_sha256'] for e in row['compiler_execs'] if e['crate']==k)
        assert argv(normal)==argv(late)
    return rows['provider-late']['after']['provider']['mtime_ns']-rows['provider-late']['after']['reader']['mtime_ns']
gap=check_order(data['publication'],'')
for i in ('plain-first-repeat','plain-second-repeat'):
    assert names(data['publication'][i])==[]
x=data['inherited_impl']
for name,rc in (('original',0),('remove-impl',101),('restore-impl',0)):
    assert x[name]['status']==x[name+'-empty']['status']==rc
    assert x[name]['sources']['reader/src/lib.rs']==x['original']['sources']['reader/src/lib.rs']
assert names(x['restored-immediate'])==[]
api(x,"remove-impl","remove-impl-empty","E0277")
p=data.get('pilot',data['publication'])
api(p,'api-incompatible-warm' if arm=='parent' else 'api-incompatible','api-incompatible-empty','E0308')
assert names(p['missing-existing-output'])==['reader'] and p['missing-existing-output']['status']==0
if arm=='parent':
    assert check_order(p,'fd-')>0 and gap>0
    for name in ('provider-late','provider-first'):
        assert p[name]['ordering']==[] # Initial pathname-only observer never reached the actual FD call.
    assert p['normal-untraced']['compiler_execs'] is None
    assert names(p['normal-untraced-first-repeat'])==[]
print(json.dumps({"all_passed":True,"arm":arm,"workspace_checks":sum(len(g) for g in data.values()),"final_late_provider_minus_reader_ns":gap,"late_repeat_rustcs":names(data['publication']['provider-late-first-repeat']),"second_repeat_rustcs":names(data['publication']['provider-late-second-repeat']),"ordinary_source_controls":["E0308","E0277","missing-output"]},sort_keys=True))

assert arm=="candidate"
bound=identity["candidate"]
assert bound["candidate"]==identity["observed_sha256_verification"]=="2eb7e548957363bfb5e4341ce1bfc312f5f5b875f881ae3d3a478531e0ddd76d"
assert bound["bytes"]==75500944 and bound["source"]=="b3360c5eda186845b9a2ba6e5330a97c07d4acf2" and bound["parent"]==identity["stock_cargo"]
assert identity["producer_receipt_sha256"]=="9780ce7fc9c85ad20d0d03b31e79a9bd0561eed6fc08a06bdfea53ed73bb880f"
assert identity["parent_packet_manifest_sha256"]=="4d00a4f2054ce96f413e7d1170ab4b2798eb0db05622073d71b25432e834153d"
p=json.loads(gzip.decompress((root/'same-path-parent.json.gz').read_bytes()))
c=data['publication']
for n in ('plain','provider-first','provider-late'):
    a,b=p[n],c[n]
    assert a['sources']==b['sources']
    assert [e['original_argv_sha256'] for e in a['compiler_execs']]==[e['original_argv_sha256'] for e in b['compiler_execs']]
    for u in ('provider','reader'):
        for at in ('before','after'):
            assert a[at][u]['sha256']==b[at][u]['sha256']
assert names(p['provider-late-first-repeat'])==['reader']
assert names(c['prior-complete-state'])==names(c['prior-complete-state-repeat'])==[]
assert any(bound["candidate_only_compiled_diagnostic"] in n for n in c["provider-late"]["cargo_notes"])
assert not any(e['role']=='reader' and e['restore'] for e in c['provider-late']['ordering'])
assert any(e['role']=='reader' and e['restore'] for e in c['provider-first']['ordering'])
f=json.loads(gzip.decompress((root/'producer-failure.json.gz').read_bytes()))
for arm,rows in f.items():
    for x in ('broken','broken-repeat','broken-empty'):
        assert rows[x]['status']==101 and rows[x]['diagnostics']==rows['broken-empty']['diagnostics']
        assert any(m['unit']=='provider' and m['code']=='E0308' for m in rows[x]['diagnostics'])
    for x in ('repaired','repaired-repeat','repaired-empty'):
        assert rows[x]['status']==0 and rows[x]['diagnostics']==[]
    assert names(rows['repaired-repeat'])==[]
print(json.dumps({"cross_arm_source_argv_metadata_equal":True,"exact_retained_parent_repeat_rustcs":names(p['provider-late-first-repeat']),"candidate_repeat_rustcs":names(c['provider-late-first-repeat']),"compared_producer_failure_checks":sum(map(len,f.values())),"candidate_checks":len(f['candidate'])+sum(len(g) for g in data.values())},sort_keys=True))

files=json.loads((root/'all-workspace-files.json').read_text())
assert files['parent']==files['candidate']
source=files['parent']
assert source['plain']==source['provider-first']==source['provider-late'] and len(source['initial'])==8
assert sorted(k for k,v in source['initial'].items() if v!=source['plain'][k])==['provider/flag','reader/src/lib.rs']
