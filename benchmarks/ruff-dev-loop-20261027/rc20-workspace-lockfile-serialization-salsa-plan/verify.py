"""Reconstruct all native activations and locked reads from the projected kernel events."""
from pathlib import Path
import base64, collections, gzip, hashlib, json, tomllib
ROOT = Path(__file__).resolve().parent
def sha(data):
    return hashlib.sha256(data).hexdigest()
def blob(name):
    value = (ROOT / name).read_bytes()
    return gzip.decompress(value) if name.endswith('.gz') else value
def load(name):
    return json.loads(blob(name))
plan, src, rows = load('protocol.json'), load('source.json.gz'), load('native.json.gz')
hist = plan['history']
assert plan['physical_protocol_sha256'] == '281fc17976c5a77479822792488aa49d6ce451a15ddffb1c4815cb731e32058e'
assert plan['native_qualification'] == src['checked_native_terminal'] == 'aa706e767257b483858cbe487680671059fac48c71d0e864e4fff9efe5016de8'
assert src['edit'] == hist['historical'] == 'c890b04e575809cbff9b43975175b43dd82c3a1a'
assert src['ruff'] == hist['ruff'] == '93526150df078af7dd8fc4226cdcc469539d2001'
assert sha(blob('historical.patch')) == hist['manifest_patch'] == src['patch']
original, older = blob('original-manifest.toml.gz'), blob('reversed-manifest.toml.gz')
key = b'salsa = { version = "0.28.'
assert len(original)==len(older)==19147 and original.count(key+b'5"')==1
assert original.replace(key+b'5"', key+b'2"') == older
assert sha(original) == hist['original'] and sha(older) == hist['reversed']
chunks = {k: base64.b64decode(v, validate=True) for k,v in load('read-chunks.json.gz').items()}
assert all(sha(v)==k for k,v in chunks.items())
order = plan['schedule']
for end in ('reverse','reverse-repeat','restore','restore-repeat'):
    sub = [v for v in order if v['endpoint']==end]
    assert [v['pair'] for v in sub]==list(range(1,9))
    assert collections.Counter(v['order'] for v in sub)=={'AB':4,'BA':4}
expected_keys = {'C/cold','C/settled'} | {f'{a}/{s}' for a in 'APS' for s in ('seed-migration','settled','reverse','reverse-repeat','restore','restore-repeat')}
assert set(rows)==expected_keys
saved = set()
shared_products, callers = set(), set()
for key,r in rows.items():
    a,phase=key.split('/')
    role='A' if a=='C' else a
    entry=src['cargo'][role]
    assert r['cargo']==entry['image'] and r['observer']==entry['observer']
    assert r['root']==hist['reversed' if phase.startswith('reverse') else 'original']
    assert r['lock']==src['lock']==plan['toolchain']['lockfile']
    assert r['kind']==['ruff_text_size',['lib'],[]] and r['finished']=={'reason':'build-finished','success':True}
    assert r['fresh']==(phase!='cold') and r['reader_stdout']=='17 29 12\n' and not r['reader_stderr']
    files=r['products'];assert set(files)=={'.rlib','.rmeta'}
    shared_products.add(tuple(sorted(files.items())));callers.add(r['reader'])
    seq=0; enrolled=None; funcs=[]; opened={}; inputs=[]; execs=[]
    for n,event,t,*v in r['wire']:
        assert n==seq+1;seq=n
        if event=='ENROLLED':
            assert enrolled is None;enrolled=t
        elif event=='EXEC':
            j=str(v[0]);executed=r['processes'][j][0];execs.append(executed)
            if executed in ('cargo','rustup'):
                av=r['argv'][j]['plain']
                if executed=='rustup':
                    assert av[0]=='+ohm';av=av[1:]
                assert av==['build','-p','ruff_text_size','--locked','--offline','--message-format=json']
        elif event=='FUNCTION':
            assert t==enrolled;funcs.append((v[0],int(v[1],16)))
        elif event=='OPEN':
            ident,fd,dev,ino,size=v
            assert ident not in opened and size==138994
            opened[ident]=[0,bytearray(),False]
        elif event=='FLOCK':
            ident,op,status=map(int,v);fd=opened[ident]
            assert status==0 and (fd[0],op) in ((0,5),(1,8))
            if op==8: assert fd[2] and len(fd[1])==138994
            fd[0]+=1
        elif event=='READ':
            ident,req,actual,cs=v;fd=opened[ident]
            assert fd[0]==1 and not fd[2] and 0<=actual<=req
            if actual:
                assert len(chunks[cs])==actual;fd[1].extend(chunks[cs])
            else:
                assert cs is None;fd[2]=True
        elif event=='CLOSE':
            fd=opened.pop(int(v[0]));assert fd[0]==2 and fd[2] and sha(fd[1])==r['lock'];inputs.append(bytes(fd[1]))
        elif event=='RESULT':
            assert v==['0'] and n==r['wire'][-1][0]
    assert r['wire'][-1][1]=='RESULT' and enrolled is not None and not opened
    assert execs[:2]==['rustup','cargo']
    compiles=[v['crate'] for v in r['argv'].values() if v['source']]
    assert (compiles, set(execs[2:]))==((['ruff_text_size'], {'rustc'}) if phase=='cold'else([],set()))
    miss=phase in ('reverse','restore','cold') or key=='P/seed-migration'
    calls=collections.Counter(name for name,_ in funcs)
    assert len(inputs)==(4 if miss else 1)
    saved.update(inputs)
    assert calls['full_workspace']==int(miss) and calls['mark_workspace']==int(miss) and calls['engine']==1+int(miss)
    s=entry['symbols']
    ser=[ret for name,ret in funcs if name=='serialize']
    assert ser==([s['return_write']]+([] if role=='S'else[s['return_mark']]) if miss else [])
    assert (r['marker'][0]!=r['marker'][1])==miss
assert len(saved)==len(shared_products)==len(callers)==1
lock=tomllib.loads(saved.pop().decode())['package']
assert len(lock)==553 and sum('checksum' in x for x in lock)==498
assert [(x['name'],x['version'])for x in lock if x['name']=='salsa']==[('salsa','0.28.5')]
assert src['registry_packages']==498 and src['workspace_packages']==55 and src['locked_registry_index_paths']==458
print('20 native commands. Both dependency changes ran the full resolver on all three release-profile images. Two versus one serializations, four equal locked reads on each miss, one on each hit. One real cold compile. All products and compiled reader agreed. Prospective independent schedule contains 64 commands.')
