"""Replay all 198 native Cargo outcomes and verify the read generations they certify."""
from pathlib import Path
import hashlib
import json
import re
import tarfile

here = Path(__file__).resolve().parent
sha = lambda b: hashlib.sha256(b).hexdigest()
identities = {
    'candidate': ('d67c68ee27b3529c52d66022bf273df8a119353f0856deeebd9ff63b24ffadde','ee9448c27a69a06a50abe707797637638dc6b2a226011339b35adc2b9a065b99','4fa9a18b77430bcc416e88561b6fe5797d98b996a7698b9f3bd11d4e7817a19f'),
    'released-sources': ('0ad5c2e226484334a5818c4702ccdf59a46732fc3cbe312b2f87411284b77ba2','52d5c046f570d3d61ff8bbaeff0d44798df916306110b4a2cac7fe459bc11955','4fa9a18b77430bcc416e88561b6fe5797d98b996a7698b9f3bd11d4e7817a19f'),
    'official-17': ('4e4065390403afbf4fb77b2f41fbc21c59afe3dda2337a5bbe29fda29a47dbb3','618ebac16b7d4ec01a2af89661d25b8f26ff347edbb69c6dcaa78f10115914a7','7ec5263869aed2fc9272ea7212aabbe7b272a4685f1b79af75c123daff09c02c'),
}

def found_compiler(trace):
    lines = trace.splitlines()
    launches = []
    for line in lines:
        if b'execve(' in line and b'/toolchains/ohm/bin/rustc", [' in line and b'"--crate-name", "hold_direct"' in line:
            if line.endswith(b'<unfinished ...>'):
                pid = line.split(maxsplit=1)[0]
                resumed, = [v for v in lines if v.startswith(pid + b' <... execve resumed>')]
                assert resumed.endswith(b'= 0')
            else:
                assert line.endswith(b'= 0')
            launches.append(line)
    return launches

totals = [0, 0, 0]
for host, arms in [('h1', ('candidate','released-sources')), ('h2', ('official-17',))]:
    with tarfile.open(here / (host+'.tar.gz'), 'r:gz') as archive:
        members = archive.getmembers()
        assert len(members) == len({m.name for m in members})
        assert all(m.isfile() and m.size < 4*1024**2 and not Path(m.name).is_absolute() and '..' not in Path(m.name).parts for m in members)
        files = {m.name: archive.extractfile(m).read() for m in members}
    index = json.loads(files.pop('index.json'))
    assert index == {k:[len(b),sha(b)] for k,b in files.items()}
    assert len(index) == (1123 if host=='h1' else 572)
    reg = json.loads(files['protocol/registration.json'])
    assert reg['public']=='17c7526dc1e5582a2728bcae6ec7ab290610c721'
    assert sha(files['protocol/SHA256SUMS']) == reg['manifest'] == '6292592a30cbd7ab35385f609845becda7d4a243b451ca305264adb26f61a5d1'
    for line in files['protocol/SHA256SUMS'].decode().splitlines():
        digest, n = line.split('  ',1)
        assert sha(files['protocol/'+n])==digest
    for arm in arms:
        ident=json.loads(files[arm+'/identity.json'])
        assert tuple(ident[n] for n in ('cargo','driver','frontend')) == identities[arm]
        compiled=json.loads(files[arm+'/complete.json'])
        assert compiled==json.loads((here/(arm+'.json')).read_bytes()) and len(compiled)==12
        for label, summary in compiled.items():
            pre=arm+'/'+label+'/'; case=json.loads(files[pre+'report.json'])
            trained=case['trained'];kind=case['kind'];stamp=case['stamp']
            assert label==('trained' if trained else 'first')+'-'+kind+'-'+stamp
            payload=lambda n:bytes((255,n)) if kind=='include-bytes' else str(n).encode()
            before,after=case['before'],case['after']
            assert before['size']==after['size']==2 and before['inode']!=after['inode']
            assert before['sha256']==sha(payload(17)) and after['sha256']==sha(payload(29))
            assert (before['mtime']==after['mtime']) if stamp=='preserved' else (before['mtime']<after['mtime'])
            assert files[pre+'private-input.txt']==payload(29) and files[pre+'observed']==b'17' and files[pre+'release']==b'1'
            current=files[pre+'caller.rs']
            original=current.replace(b'println!("revision=2");',b'')
            assert trained==(current!=original)
            stale=trained or (arm=='candidate' and kind=='tracked-file')
            for phase in (['train1','train2','train3'] if trained else [])+['change','repeat','again','clean']:
                prefix=pre+phase+'/'; row=json.loads(files[prefix+'row.json'])
                assert case['rows'][phase]==row
                assert row['caller_sha']==sha(original if phase.startswith('train') else current)
                records=[json.loads(s) for s in files[prefix+'cargo.jsonl'].splitlines()]
                assert records[-1]=={'reason':'build-finished','success':True}
                artifacts=[v for v in records if v['reason']=='compiler-artifact']
                caller,=[v for v in artifacts if v['target']['name']=='hold_direct']
                trace=files[prefix+'exec']; launch=found_compiler(trace)
                assert (caller['fresh'],len(launch),all(v['fresh'] for v in artifacts))==(row['fresh'],int(not row['fresh']),row['all_fresh'])
                if phase=='change': assert len(launch)==1
                if phase=='train3': assert row['fresh'] and row['initially_complete']
                for field,name in [('trace','exec'),('dep','rustc.d'),('native','program'),('fingerprint','fingerprint')]:
                    assert row[field]==sha(files[prefix+name])
                dep=files[prefix+'rustc.d']; proof=files[prefix+'fingerprint'];std=files[prefix+'program']
                assert proof[-41:-37]==b'OBS1' and bool(proof[-33])==row['initially_complete']
                headers=[l for l in dep.splitlines() if l.startswith(b'# ohm-observer-inputs-v1 ')]
                assert bool(headers)==row['optional'] and len(headers)<=1
                full=bytes.fromhex(headers[0].split(b' ')[3].decode()) if headers else dep
                checks=[s.decode() for s in full.splitlines() if s.startswith(b'# checksum:') and s.endswith(b'/private-input.txt')]
                assert checks==row['input_checksums']
                actual,=re.findall(rb'^sample=(\d+)$',std,re.M)
                expected=17 if phase.startswith('train') or phase=='change' or (phase in ('repeat','again') and stale) else 29
                assert row['value']==int(actual)==expected
                assert (b'revision=2' in std.splitlines())==(trained and not phase.startswith('train'))
                assert summary[phase]==[row['value'],row['fresh'],row['initially_complete'],row['untrackable']]
                if phase in ('repeat','again') and stale:
                    assert row['fresh'] and row['all_fresh'] and row['exe']==case['rows']['change']['exe']
                    totals[2]+=1
                if phase=='change' and stale:
                    checksum,=checks
                    known='b5d1e70f1eaa471a592b91e695b13d181156521c31840321052f937a87937658' if kind=='include-bytes' else '26ef00fd9555bd7513a82faef1b56c9d1efd61bc84e311e6ed902c79c40602c4'
                    assert checksum.startswith('# checksum:blake3='+known+' file_len:2 ') and row['initially_complete']
                if phase in ('again','clean'):
                    replay=json.loads(files[prefix+'replay.json'])
                    assert (replay['executable'],replay['sha256'],replay['stdout'].encode())==(caller['executable'],row['exe'],std)
                    assert replay['size']>10000
                    totals[1]+=1
                totals[0]+=1
assert totals==[198,72,40], totals
print('198 Cargo invocations, 72 end-state executable replays and 40 wrong-fresh unchanged builds independently verified.')
