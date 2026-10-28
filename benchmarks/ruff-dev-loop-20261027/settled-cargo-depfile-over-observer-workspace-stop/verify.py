"""Validate the sealed sources, genuine native outcomes and real cache replacements."""
import ast,gzip,hashlib,json,re
from pathlib import Path
P=Path(__file__).resolve().parent
h=lambda b:hashlib.sha256(b).hexdigest()
def load(name):
    p=P/(name+'.gz');return json.loads(gzip.decompress(p.read_bytes()))
def raw(name):return gzip.decompress((P/(name+'.gz')).read_bytes())
def jsonfile(name):return json.loads((P/name).read_bytes())
def sources():
    sums=(P/'SHA256SUMS').read_text().splitlines();listed={}
    for l in sums:
        digest,name=l.split('  ',1);assert name not in listed;listed[name]=digest;assert h((P/name).read_bytes())==digest,name
    assert set(listed)=={str(p.relative_to(P)) for p in P.rglob('*') if p.is_file() and p.name!='SHA256SUMS'}
    # Raw observations can legitimately contain the registry host; public bytes are deidentified.
    bind=jsonfile('raw-to-portable.json')
    for name,keys in bind.items():assert h(raw(name))==keys[1]
    for d in ('first-rejection','second-rejection'):
        for n,(old,new) in [(name,(entry['original'],entry['portable']) if isinstance(entry,dict) else entry) for name,entry in jsonfile(d+'/original-digests.json').items()]:
            assert h(raw(d+'/'+n))==new
    return bind
B=sources()
v=load('rejected-ancestor-v1.json');second=load('rejected-union-v2.json');keys=load('offline-key-families.json');plan=load('union-plan.json')
assert v['initial_slots']==0 and len(v['products'])==922 and len(v['public_deps'])==58 and second['zero']
assert second['route_permissions']=='0o700' and len(second['all_current'])==732 and keys['covered_manifests']==370 and keys['cached_by_stamp']=={'pgo':366,'stock':366}
assert h((P/'prime-union.py').read_bytes())==plan['coordinator'] and h(raw('union-plan.json'))=='462e9db68f8672c0503eff00fced28c6687f5cb48e528bca2dc2439f9763b233'
for f in ('offline-key-families','rejected-union-v2','rejected-ancestor-v1'):
    assert B[f+'.json'][0]==plan['prerequisite_digests'][f+'.json']
def fixed_output(output,control):
    items=[json.loads(line) for line in raw(output).splitlines()];units=[r for r in items if r['reason']=='compiler-artifact']
    assert len(units)==501 and all(r['fresh'] for r in units) and not any('ron@' in x['package_id'] for x in units)
    assert {f for r in units for f in r['filenames']}==set(v['products'])
    assert units and b'Finished' in raw(control)
def results(d):
    n='union-native-v3/'+d+'/';r=load(n+'record.json');native=load(n+'observed.json');before=load(n+'before.json');after=load(n+'after.json')
    fixed_output(n+'stdout',n+'stderr')
    assert [r['units'],r['products'],r['depfiles'],r['source'],r['git_index']]==[501,922,58,v['source'],v['index_sha']]
    arm=d.split('-')[1];assert r['cargo']==(plan['subjects'][arm] if arm!='stock' else '4e4065390403afbf4fb77b2f41fbc21c59afe3dda2337a5bbe29fda29a47dbb3')
    assert len(native['exec'])==len(r['exec'])==2 and native['exec']==r['exec'] and all(x.endswith('/bin/cargo') for x in r['exec'])
    assert r['before']==B[n+'before.json'][0] and r['after']==B[n+'after.json'][0] and r['observed']==B[n+'observed.json'][0] and r['stdout']==B[n+'stdout'][0]
    assert set(r['reads'])=={'.ohm-git-index-sha1dc-v1','.ohm-registry-json-v2'} and r['reads']=={k:len(a) for k,a in native['reads'].items()}
    lines=load(d+'/proof-syscalls.json'); assert all(pid in native['trace'] for pid,l in lines)
    actual_reads={}
    for kind in r['reads']:
        slots={m[1] for _,l in lines if l.startswith('openat(') and 'O_RDONLY' in l and (m:=re.search(re.escape('/'+kind+'/')+r'([a-f0-9]{3,64})"', l))}
        assert sorted(slots)==native['reads'][kind] and slots;actual_reads[kind]=len(slots)
    header={};first_key={};installs=[]
    for pid,l in lines:
        m=re.match(r'write\(\d+<([^>]+)>, "(.*)", (21|32)\)\s+=\s+(21|32)$',l)
        if m:
            tmp=m[1];buf=ast.literal_eval('b"'+m[2]+'"')
            if len(buf)==21:assert buf==b'ohm-registry-json-v2\0';header[tmp]=pid
            if len(buf)==32 and tmp not in first_key:assert header[tmp]==pid;first_key[tmp]=buf.hex()
        if l.startswith(('rename','link')):
            src,dst=re.findall(r'"([^"]+)"',l)[-2:];assert re.fullmatch(r'[0-9a-f]{3}',Path(dst).name)
            k=first_key[src];mapping=[(name,arm) for name,items in keys['each_expected_key'].items() for arm,hx in items.items() if hx==k];assert len(mapping)==1
            installs.append([pid,Path(dst).name,k,list(mapping[0])])
    assert installs==r['installs']==native['install']
    assert (r['writes']==0)==(not installs) and r['writes']==len(native['writes'])
    return r,before,after,installs
zero=jsonfile('zero.json');assert zero['original_reject_not_modified'] and zero['trust_parent'] and not zero['trust_candidate_exists'] and not zero['terminal']
assert not any(zero['grants'].values()) and all(i==0 for i in zero['recorded_slots'].values())
for arm in ('stock','parent'):
    j='second-rejection/trusted-ancestor-v2/normal-'+arm+'/'
    fixed_output(j+'stdout',j+'stderr')
old=load('first-rejection/qualified-261-workspace/workspace/qual/trace-parent/record.json')
assert old['units']==501 and len(old['products'])==922 and len(old['physical'])==2
rows={};prev=None
for stage in ('prime','verify'):
 for arm in ('stock','parent','candidate'):
    d=stage+'-'+arm;r,before,after,entries=results(d);rows[d]=r
    if prev is not None:assert before==prev
    prev=after
    if d=='prime-candidate':
        primed=load('union-native-v3/primed.json');assert after==primed and len(primed)==740
    if stage=='verify':
        assert {k:t[0] for k,t in before.items()}=={k:t[0] for k,t in after.items()}
        if arm=='stock':assert not entries and before==primed==after
        else:
            assert [e[3] for e in entries]==[['notify-8.2.0','pgo'],['rand_core-0.10.0','pgo']]
            assert [e[1] for e in entries]==['3d1','3d1'] and [e[2][:6] for e in entries]==['6a03d1','d873d1']
            assert [k for k in before if before[k]!=after[k]]==['.ohm-registry-json-v2/3d1']
done=load('union-native-v3/union.json');assert not done['eligible'] and done['zero_scored'] and [r[0] for r in done['failures']]==['parent','candidate'] and raw('union-qualification.rc').strip()==b'0'
assert done['rows']==[B['union-native-v3/'+d+'/record.json'][0] for d in rows]
print('All six 501-unit ordinary commands retained the 922-product roster; verified two exact replacements at slot 3d1 in each matched arm, none in stock. H8 correctly stopped with zero instruction observations.')
