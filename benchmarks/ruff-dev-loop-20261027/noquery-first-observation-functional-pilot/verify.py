"""Verify the native claims and source binding. Run next to the packet."""
from pathlib import Path
import hashlib,json
p=Path(__file__).resolve().parent;s=json.loads((p/'observations.json').read_bytes());c=s['small']
d=lambda row,kind:sum(v['exec']==kind for v in row['processes'])
for arm in ('A-common','N-common','Q-common','N-old-raw','Q-old-raw','old-rust-cargo-baseline'):
 z=c[arm];first=z['first'];changed=z['changed'];noop=z['noop'];empty=z['empty']
 assert first['value']==17 and changed['value']==noop['value']==empty['value']==29
 assert first['stamps']==changed['stamps'] and first['real']!=changed['real']
 assert first['complete']==(arm in ('Q-common','N-common')) and first['has_optional']==(arm in ('A-common','N-common'))
 assert d(first,'observer-query')==(arm.startswith('Q-')) and d(changed,'rustc')==1 and d(noop,'rustc')==0
 assert changed['native']==noop['native']
 assert all(len(v['original_sha256']['exec'])==64 for v in z.values())
z=c['guard-switch-v2'];assert z['prime']['value']==17 and z['changed']['value']==z['old-source-edit']['value']==z['return-edit']['value']==z['empty']['value']==29
assert z['prime']['complete']==1 and z['changed']['complete']==0 and z['old-source-edit']['complete']==1
assert z['repeat']['fresh'] and z['return-fresh']['fresh']
assert all(d(v,'observer-query')==0 for v in z.values())
z=c['guard-wrapper-v3'];assert all(not v['complete'] and v['has_optional'] and sum(j.get('crate')=='hold_direct' for j in v['processes'])==1 for v in z.values())
z=c['guard-off-v2'];assert not z['prime']['complete'] and all(not v['has_optional'] for v in z.values()) and z['changed']['value']==29
for a,z in s['ron'].items():
 for k,v in z.items():
  jobs=[x for x in v['processes'] if x['exec']=='rustc']; links=[x for x in v['processes'] if x['exec']=='native-linker']
  assert d(v,'observer-query')==0 and len(v['programs'])==5 and sum(k.get('passes',False) for k in v['programs'].values())==4
  if k=='first':assert len(jobs)==27 and len(links)==15 and v['fresh']==0 and v['complete']==(a=='N')
  elif k=='second' and a=='A':assert len(jobs)==6 and sum(j['phase']=='full' for j in jobs)==1 and len(links)==5 and v['fresh']==16
  else:assert not jobs and not links and v['fresh']==v['units']==23
  for name,prog in v['programs'].items():assert prog['sha256']==z['first']['programs'][name]['sha256']
assert s['permanent']['status']==0 and any('10 passed' in row for row in s['unit'])
print('Verified 6 crossed protocol cases, in-place driver swaps, wrapper and user opt-out, 6 native registry commands, 10 Cargo units and Rust run-make')

import re, tarfile
states=json.loads((p/'native-release.json').read_bytes()); build=json.loads((p/'build-controls.json').read_bytes())
hashbytes=lambda data:hashlib.sha256(data).hexdigest()
assert set(states)=={'A-common','N-common','Q-common','N-legacy'}
assert all(build[a]['source_verified_leaves']==3108 and len(build[a]['full_compiles'])==2 for a in build)
for key in ('version','pgo','stamp','builder'):
    assert len({b[key] for b in build.values()})==1
with tarfile.open(p/'native-records.tar.gz') as t:
    read=lambda n:t.extractfile(n).read()
    assert len(t.getmembers())==106 and read('receipt.json')==(p/'native-release.json').read_bytes()
    for name,run in states.items():
        arm=name[0]; assert run['cargo']==build[arm]['binary']
        assert run['compiler']=='4fa9a18b77430bcc416e88561b6fe5797d98b996a7698b9f3bd11d4e7817a19f'
        assert run['driver']==('52d5c046f570d3d61ff8bbaeff0d44798df916306110b4a2cac7fe459bc11955' if name=='N-legacy' else s['images']['supporting_compiler'])
        rows=run['rows']; assert rows['first']['stamps']==rows['changed']['stamps'] and rows['first']['real']!=rows['changed']['real']
        assert rows['first']['complete']==rows['empty']['complete']==int(name in ('Q-common','N-common'))
        for lab,row in rows.items():
            h=f'{name}/case/records/{lab}/'
            assert read(h+'native').decode()==row['native'] and row['value']==(17 if lab=='first' else 29)
            dep=read(h+'rustc.d');fp=read(h+'fingerprint')
            assert hashbytes(dep)==row['dep_sha'] and hashbytes(fp)==row['fp_sha']
            assert fp[5]==4 and fp[-41:-37]==b'OBS1' and fp[-33]==row['complete']
            data=[json.loads(line) for line in read(h+'stdout.jsonl').splitlines()]
            target,=[v for v in data if v.get('reason')=='compiler-artifact' and v['target']['name']=='hold_direct']
            assert target['fresh']==row['fresh'] and row['fresh']==(lab=='noop')
            assert data[-1].get('success') and row['queries']==int(arm=='Q' and lab!='noop')
            complete=[];pending={}
            for raw in read(h+'exec').decode().splitlines():
                item=re.match(r'(\d+)\s+(.*)',raw)
                if not item:continue
                pid,line=item.groups()
                if line.startswith('execve('):
                    if line.endswith('<unfinished ...>'):
                        pending[pid]=line[:-len('<unfinished ...>')];continue
                elif line.startswith('<... execve resumed>'):
                    if pid not in pending:continue
                    line=pending.pop(pid)+line[len('<... execve resumed>'):]
                else:continue
                if re.search(r'= 0\s*$',line):complete.append(line)
            direct=[v for v in complete if re.match(r'execve\("[^"]+/(active-sdk|rustup/toolchains/ohm)/bin/rustc"',v)]
            assert sum('"--crate-name", "hold_direct"' in v and '"--print=' not in v for v in direct)==row['caller_full_compiles']==int(lab!='noop')
            assert sum('"-Zohm-observer-dep-info", "--print=sysroot"' in v for v in direct)==row['queries']
            assert dep.startswith(b'# ohm-raw-checksum-paths-v2\n')
            if lab in ('first','empty'):
                certs=[v for v in dep.splitlines() if v.startswith(b'# ohm-observer-inputs-v1 ')]
                assert len(certs)==(name in ('A-common','N-common'))
                ordinary=dep
                if certs:
                    hdr=certs[0];nested=bytes.fromhex(hdr.split(b' ')[3].decode())
                    assert hashbytes(nested)==run['nested_sha'] if lab=='first' else nested.startswith(b'# ohm-raw-checksum-paths-v2\n')
                    assert b'libescape_fixture.rlib' in nested and b'# checksum:' in nested
                    ordinary=dep.replace(hdr+b'\n',b'',1)
                assert (b'libescape_fixture.rlib' in ordinary)==(name=='Q-common')
                assert any(line.startswith(b'# checksum:') and line.endswith(b'incidental.rlib') for line in ordinary.splitlines())
for name,k in s['permanent']['source'].items(): assert hashbytes((p/'run-make'/name).read_bytes())==k
assert b'10 passed; 0 failed' in (p/'exact-cargo-unit.log').read_bytes()
print('Verified 16 release-built native commands, complete first observation and legacy fallback, preserved process rosters, all raw native depfiles and fingerprint receipts')
