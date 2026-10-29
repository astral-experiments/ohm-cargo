"""Reconstruct every captured lockfile read from its bytes and verify all 30 native results."""
import collections,copy,gzip,hashlib,json,re,sys,tomllib
from pathlib import Path
p=Path(__file__).resolve().parent
def h(b):return hashlib.sha256(b).hexdigest()
def read(n):return json.loads((p/n).read_bytes())
def check(allrows,s,orig):
    stale=orig.replace(b'name = "ruff_text_size"\nversion = "0.0.17"',b'name = "ruff_text_size"\nversion = "0.0.16"')
    comment=orig.replace(b'version = 4\n',b'# Independent lockfile writer.\nversion = 4\n',1)
    blobs={h(b):b for b in (orig,stale,comment,b'version = [\n')}
    H=h(orig);S=h(stale);C=h(comment);M=h(b'version = [\n')
    assert len(blobs)==4 and H==s['lock']=='c9e345325bec5ff08dbbe3916edd39ad0c3d1c7797a8c241ae32f62754e764bf'
    assert len(orig)==len(stale)==138994 and len(comment)==139025 and len(tomllib.loads(orig.decode())['package'])==553
    assert len(s['test_discovery']['units'])==19
    products={'libruff_text_size.rlib':'ca93d901b6e0be5852aa1833abe663f4bc1f57c8e8ef4d0156d1a62c1367ef59','libruff_text_size-48f333158b244f36.rmeta':'af8f228d9e5e76c736b54649f65b2d4089f01edc16ee615df49142e8f373f9a9'}
    clean_caller='9fd6acb5896e86a2c59526eb0b1c63aa1b5cdd02f8fd0f50e9f7012540a2e53d'
    assert {name:len(rows) for name,rows in allrows.items()}=={'decoder':12,'serializer':10,'returns':8}
    for name,rows in allrows.items():
      for phase,r in rows.items():
        if phase.startswith('plain-'):
          assert r['fresh'] and r['consumer']=='17 29 12' and not any(e[1] or e[2] for e in r['kernel_execs'])
          assert dict(r['files'])==products
          continue
        assert r['argv']==['cargo','+ohm','build','-p','ruff_text_size','--locked','--offline','--message-format=json']
        assert r['manifest']==s['manifest'][r['state']]
        fs={x['id']:x for x in r['open']};offset={};mode={};functions=[];serial=[];canonical=[];converted=[];dec=[];chronological=[]
        actor=r['actor'];prior=0
        for e in r['events']:
          assert e[0]>prior;prior=e[0];kind=e[1]
          if kind=='OPEN':
            i=e[2];assert i not in offset and e[3]==fs[i]['size'];mode[i]=0;offset[i]=0;chronological.append(fs[i]['sha'])
          elif kind=='FLOCK':
            i=e[2];assert e[4]==0 and e[3]==(5 if mode[i]==0 else 8);mode[i]+=1
          elif kind=='READ':
            _,_,i,want,got,digest=e;assert mode[i]==1 and 0<=got<=want
            if got:
              content=blobs[fs[i]['sha']];start=offset[i];assert h(content[start:start+got])==digest;offset[i]+=got
            else:assert digest is None
          elif kind=='CLOSE':
            i=e[2];assert mode[i]==2 and offset[i]==len(blobs[fs[i]['sha']]);mode[i]=3
          elif kind=='CHANGED':
            assert actor and actor['exclusive_acquired'] and all(v==3 for v in mode.values())
          elif kind=='FUNCTION':
            _,_,func,pc,sz,digest=e;functions.append(func)
            if digest:assert len(blobs[digest])==sz
            if func=='toml_lockfile':dec.append((pc,digest))
            if func=='into_resolve':converted.append(pc)
            if func=='serialize_resolve':serial.append((pc,digest))
            if func.startswith('encoded_at_'):canonical.append((pc,digest))
          else:assert kind in ('EXEC','RESULT')
        assert all(v==3 for v in mode.values()) and set(fs)==set(mode) and r['events'][-1][-1]==r['exit']
        assert r['native']==[] if phase!='B1-prepare' else len(r['native'])==1 and r['native'][0][:2]==['rustc','ruff_text_size']
        if r['exit']==0:
          assert r['verdict']=='success' and len(r['artifacts'])==1 and dict((k,v)for k,_,v in r['artifacts'][0]['outputs'])==products
          assert r['artifacts'][0]['fresh']==(phase!='B1-prepare')
          assert r['oracle']==[['consumer',0,'17 29 12',clean_caller]]
        else:assert r['exit']==101 and r['verdict'] in ('malformed','locked-stale')and not r['artifacts'] and not r['oracle']
        if actor:
          assert actor['original']==H and actor['changed']=={'stale':S,'malformed':M,'comment':C}[actor['mode']]
          assert actor['same_inode']==(actor['mode']!='malformed') and actor['same_length']==(actor['mode']=='stale')
        if name=='decoder':
          assert functions[0]=='cache_loader'
          if phase in ('B1-prepare','B3-reverse','B5-restore'):
            assert chronological==[H]*4 and dec==[('9f8b13',H),('9f93f7',H)] and converted==['9f8bba','9f94a1'] and r['before']!=r['after']
          elif phase=='raced-malformed':
            assert chronological==[H,M] and dec==[('9f8b13',H),('9f93f7',M)] and converted==['9f8bba'] and r['verdict']=='malformed'
          elif phase=='static-malformed': assert chronological==[M] and dec==[('9f8b13',M)] and not converted and r['verdict']=='malformed'
          elif phase.endswith('stale') and not phase.startswith('recover'):
            assert chronological==([H,S,S] if phase.startswith('raced') else [S,S,S])
            assert dec==[('9f8b13',chronological[0]),('9f93f7',S),('a796c9',S),('a79775',H)] and converted==['9f8bba','9f94a1','a7985b','a798d9'] and r['verdict']=='locked-stale'
          else:assert chronological==[H] and dec==[('9f8b13',H)] and converted==['9f8bba'] and r['before']==r['after']
        elif name=='serializer':
          if phase in ('2-reverse','4-restore'):
            assert chronological==[H]*4 and dec==[('9f8b13',H),('9f93f7',H)] and converted==['9f8bba','9f94a1'] and serial==[('a7a678',H),('a6c2d1',H)]
          else:assert chronological==[H] and dec==[('9f8b13',H)] and converted==['9f8bba'] and not serial
        elif name=='returns':
          if phase in ('1-reverse','2-restore','8-restore'):
            assert chronological==[H]*4 and serial==canonical==[('a7a678',H),('a6c2d1',H)]
          elif phase in ('3-raced-stale','6-raced-comment'):
            changed=actor['changed'];assert chronological==[H,H,H,changed] and serial==[('a7a678',H),('a6c2d1',changed)]
            assert canonical==[('a7a678',H),('a6c2d1', H if changed==S else C)]
            assert (r['before']==r['after'])==(changed==S)
          elif phase=='4-static-stale':assert chronological==[S]*3 and canonical==[('a7a678',H)] and r['verdict']=='locked-stale'
          else:assert chronological==([C]if phase=='7-unchanged-comment'else[H]) and not serial and not canonical
    return '30 Cargo builds verified, including both genuine profile transitions, 5 plain controls and 4 synchronized writer actions'

if __name__=='__main__':
    if (p/'SHA256SUMS').exists():
        for line in (p/'SHA256SUMS').read_text().splitlines():
            sha,n=line.split('  ',1);assert Path(n).name==n and h((p/n).read_bytes())==sha
    data=json.loads(gzip.decompress((p/'commands.json.gz').read_bytes()));subjects=read('subjects.json');source=gzip.decompress((p/'original-lockfile.gz').read_bytes())
    print(check(data,subjects,source))
    if '--self-test'in sys.argv:
        for group,label,target in [('decoder','B3-reverse','toml_lockfile'),('returns','3-raced-stale','encoded_at_mark')]:
            bad=copy.deepcopy(data)
            row=bad[group][label];y=next(e for e in row['events'] if e[1:3]==['FUNCTION',target])
            row['events'].remove(y)
            try:check(bad,subjects,source)
            except AssertionError:continue
            raise AssertionError('accepted corrupted '+label)
        print('rejected both missing-event mutations')
