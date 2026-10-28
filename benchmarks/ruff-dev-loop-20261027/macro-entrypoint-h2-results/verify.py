"""Recompute the work and byte-identity comparisons for the registered two-arm probe."""
from pathlib import Path
import ast,collections,gzip,hashlib,json,re,tarfile

p=Path(__file__).resolve().parent;sha=lambda data:hashlib.sha256(data).hexdigest();table=json.loads(gzip.decompress((p/'inventory.json.gz').read_bytes()))
with tarfile.open(p/'observations.tar.gz') as t:mem={m.name:t.extractfile(m).read() for m in t if m.isfile()}
assert set(mem)==set(table['members']) and len(mem)==514
for name,data in mem.items():
    old,new,olen,nlen,count=table['members'][name];assert len(data)==nlen and sha(data)==new and count==data.count(table['alias'].encode())
    if not count:assert old==new and nlen==olen
get=lambda f:json.loads(mem[f]);assert get('registration.json')['commit']=='d4c6a2c698432668c65acf6c725a6dd3d25af037' and get('setup/previous-registration.json')['commit']=='eec15990f6bbae96c0c78d23d27c64a59cf8075c' and b"'--print','sysroot'" in mem['setup/previous-failure.txt']
phases=['cold','settled','format','format-repeat','format-restore','diagnostic','diagnostic-repeat','diagnostic-restore','used','used-repeat','used-restore','final'];edits={'format','format-restore','diagnostic','diagnostic-restore','used','used-restore'};summary={};physical=collections.Counter()
execve=re.compile(rb'^execve\(("(?:[^"\\]|\\.)*"),\s*(\[.*\]),\s*(?:0x[\da-f]+|NULL).*?\)\s+= 0$')
for arm,links in [('build',1),('test',2)]:
    prior=None;roster=None;elf={};listing=None;terminal=get(arm+'/complete.json');assert terminal['mode']==arm and [r['phase'] for r in terminal['phases']]==phases and not mem[arm+'/summary.stderr']
    for phase,obs in zip(phases,terminal['phases'],strict=True):
        b=arm+'/'+phase+'/';assert get(b+'result.json')==obs
        records=[json.loads(s) for s in mem[b+'cargo.stdout'].splitlines()];assert records[-1]=={'reason':'build-finished','success':True}
        units=[r for r in records if r['reason']=='compiler-artifact'];assert len(units)==obs['units']==52 and sum(r['fresh'] for r in units)==obs['fresh']
        lineage=sorted(json.dumps({k:r[k] for k in ('package_id','manifest_path','target','profile','features','filenames','executable')},sort_keys=True) for r in units)
        if roster is None:roster=lineage
        assert lineage==roster
        products=get(b+'products.json')
        reported={f for u in units if u['package_id'].startswith('path+file:') for f in u['filenames']+([u['executable']] if u['executable'] else [])};assert set(products)==reported and table['members'][b+'products.json'][0]==obs['products']
        changed={n for n in products if prior is not None and prior[n]!=products[n]};assert changed==set(obs['changed']);prior=products
        proc=get(b+'native.json');assert table['members'][b+'native.json'][0]==obs['native'];counts=collections.Counter(r['kind'] for r in proc);assert counts==obs['physical'];physical.update(counts)
        for r in proc:
            raw=mem[b+'trace/'+r['pid']].splitlines();assert raw[-1]==b'+++ exited with 0 +++' and r['exit']==0
            hits=[line for line in raw if (m:=execve.match(line)) and ast.literal_eval(m[1].decode())==r['exe'] and ast.literal_eval(m[2].decode())==r['argv']]
            assert len(hits)==1 and table['exec_lines'][sha(hits[0])]==r['raw']
        dso,=[f for r in units if r['target']['kind']==['proc-macro'] and r['target']['name']=='ruff_macros' for f in r['filenames'] if f.endswith('.so')];assert products[dso]==obs['dso']
        expected=(b'4294967293\n' if obs['variant']=='used' else b'4294967294\n');assert mem[b+'direct-run.stdout']==expected and not mem[b+'direct-run.stderr'] and not mem[b+'direct-compile.stderr']
        words=(b'non-blank' if obs['variant']=='diagnostic' else b'non-empty');assert b'expected prefix string to be '+words in mem[b+'negative-compile.stderr']
        if arm=='build':
            assert mem[b+'reexport-run.stdout']==expected and not mem[b+'reexport-compile.stderr'] and not mem[b+'reexport-run.stderr']
        else:
            exe,=[r['executable'] for r in units if r['target']['name']=='ruff_index' and r['profile']['test'] and r['executable']];elf[phase]=products[exe];current=mem[b+'test-list.stdout'];assert current.count(b': test\n')==5 and not mem[b+'test-list.stderr']
            if listing is None:listing=current
            assert listing==current
        if phase=='cold':assert counts=={'full':52,'wild':(11 if arm=='build' else 12)} and obs['fresh']==0
        elif phase in edits:
            assert counts=={'full':2,'wild':links} and obs['fresh']==50 and {r['name'] for r in proc if r['kind']=='full'}=={'ruff_macros','ruff_index'}
            assert dso in changed
            if arm=='build':assert {Path(f).suffix for f in changed}=={'.so','.rmeta','.rlib'} and len(changed)==3
            else:assert changed==({dso,exe} if phase in ('used','used-restore') else {dso})
        else:assert obs['fresh']==52 and not counts and not changed
    if arm=='test':
        base=elf['settled'];assert all(h==base for n,h in elf.items() if n not in ('used','used-repeat')) and elf['used']==elf['used-repeat']!=base
    summary[arm]={'commands':len(phases),'whole_compiles_per_edit':2,'links_per_edit':links,'test_binary_sha256':elf.get('settled')}
print(json.dumps({'arms':summary,'physical':dict(physical)},sort_keys=True))
