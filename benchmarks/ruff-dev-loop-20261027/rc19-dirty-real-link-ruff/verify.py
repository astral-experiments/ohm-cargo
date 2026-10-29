from pathlib import Path
import gzip,hashlib,json
s=Path(__file__).resolve().parent
for l in (s/'SHA256SUMS').read_text().splitlines():
 d,n=l.split('  ',1);assert hashlib.sha256((s/n).read_bytes()).hexdigest()==d,n
rows=json.load(gzip.open(s/'observations.json.gz'));scope=json.loads((s/'scope.json').read_bytes());p=rows['matched_parent'];c=rows['candidate'];g='generate_inline_tests';f='fixtures'
def count(r):return tuple(sum(x['tag']==z for x in r['rustc']) for z in ('full','link-only'))+(len(r['native']),)
def check_zero(r):assert count(r)==(0,0,0) and all(x['fresh'] for x in r['typed'])
assert len(p)==9 and len(c)==12 and scope['matched_parent']['cargo'].startswith('bd4b4545') and scope['candidate']['abi']['bin/cargo'].startswith('99383612')
for a in (p,c):
 for j in (1,3,5,7):check_zero(a[j])
 assert a[0]['programs'][f]['listed']==558 and a[2]['programs'][f]['listed']==557 and a[4]['programs'][f]['listed']==558
 assert all(x['programs'][g]['list_exit']==0 and all(t['one_passed'] for v in x['programs'].values() for t in v['tests']) for x in a[:6])
for j in (2,4,6):assert count(p[j])==(1,1,1) and count(c[j])==(1,2,2)
assert p[6]['programs'][g]['list_exit']==0 and p[6]['programs'][f]['list_exit']==83 and p[8]['exit']==0 and not p[8]['native']
assert all(c[6]['programs'][n]['list_exit']==c[7]['programs'][n]['list_exit']==83 for n in (g,f)) and all(c[i]['exit']==101 and c[i]['contains_native_error'] and len(c[i]['native'])==1 for i in (8,9))
assert c[10]['programs'][g]['sha256']==c[0]['programs'][g]['sha256'] and c[10]['programs'][g]['list_exit']==0;check_zero(c[11])
a=rows['candidate_defaults_off'];assert len(a)==4 and all(a[1]['programs'][n]['list_exit']==83 for n in (g,f)) and a[2]['exit']==101 and a[2]['native'] and a[3]['programs'][g]['list_exit']==0
a=rows['candidate_ron'];assert [count(a[i]) for i in (1,2,4)]==[(1,2,2)]*3 and count(a[3])==count(a[5])==(2,2,2) and all(i['programs'][g]['tests'][0]['one_passed'] for i in a)
e=rows['candidate_e2e'];assert len(e)==6 and len(e[0]['typed'])==300 and count(e[2])==(1,1,1) and e[4]['exit']==101 and 'E0308' in e[4]['errors'] and not e[4]['native'] and e[0]['programs']['e2e']['sha256']==e[5]['programs']['e2e']['sha256']!=e[2]['programs']['e2e']['sha256'];check_zero(e[1]);check_zero(e[3])
for z in (e[0],e[1],e[2],e[3],e[5]):assert z['programs']['e2e']['listed']==200 and len(z['programs']['e2e']['tests'])==2 and all(v['one_passed'] for v in z['programs']['e2e']['tests'])
for name in ('valid','invalid'):
 v=scope['empties'][name];z,=rows['candidate_empty_'+name];assert v['initial_target_files']==v['initial_shared_files']==0 and v['published_before_actual_link'] and v['real_search_exact']
 if name=='valid':assert z['programs'][g]['list_exit']==83
 else:assert z['exit']==101 and z['contains_native_error']
assert sum(map(len,rows.values()))==39 and all(x['raw_sha256'] for a in rows.values() for x in a);print('Verified 39 real Ruff commands, both source-matched development Cargo images, RON features, independent empty native values/failure, fresh repeats and actual ty_server:e2e edit/invalid/restoration.')
