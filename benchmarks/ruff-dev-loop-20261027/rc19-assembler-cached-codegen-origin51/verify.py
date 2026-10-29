"""Check all historical product flags, process identities, real verdicts, and input bytes."""
import hashlib,json,re
from pathlib import Path
p=Path(__file__).resolve().parent
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def read(path):return json.loads(path.read_bytes())
sources=read(p/'sources.json')
pr=read(p/'pr51.json'); assert pr['number']==51 and pr['base_ref']=='charlie/1.98/rdr-semantic-generations' and pr['head_ref']=='charlie/1.98/rdr-rlink-cache'
before='30004d93bdf3b07003fb8cd7097be81d862a9f41'; after='caac2566f0fbdf3984f519c2141a6d78e18b01b2'
assert pr['base']==before and pr['head']==after and sources['after']['parents']==[before]
assert sources['before']['source']==before and sources['after']['source']==after
assert sources['before']['Cargo.lock']==sources['after']['Cargo.lock']
assert sources['before']['Cargo.toml']==sources['after']['Cargo.toml']
assert {sources[k]['features'][0] for k in ['after','before']}=={'default'}
release=read(p/'release.json')
sdk=read(p/'historical-sdk-verified-full.json'); assert sdk['archive_sha256']=='d1bf93f2db9cf55b25a4c66410caf1a02e3beabecd3cbdca47d9423b9583f465'
artifact,=[a for a in release['assets'] if a['name'].endswith('.tar.gz')]
assert artifact['digest']=='sha256:'+sdk['archive_sha256'] and artifact['size']==sdk['archive_bytes']==304680519
assert len(sdk['checked'])==66 and sdk['source']['rust']['revision']=='f6270311094cd4b48fefce03debdffcf8396c64c'
assert sdk['checked']['lib/rustlib/x86_64-unknown-linux-gnu/bin/rust-lld'].startswith('8fdb035a0d873')
orders=('before-public-only','after-relink','after-public-only')
seen=[];global_inputs={}
for arm in orders:
    based=p/'arms'/arm
    terminal=read(based/'terminal.json');assert len(terminal['phases'])==10 and terminal['rustc']==sdk['checked']['bin/rustc']
    role='before' if arm==orders[0] else 'after'
    info=sources[role]; assert info['product']==terminal['cargo']
    assert ('commit-hash: '+info['source']+'\n') in (based/'cargo-version').read_text()
    assert sha(based/'cargo-version')==terminal['versions']['cargo'] and sha(based/'rustc-version')==terminal['versions']['rustc']
    assert terminal['cargo_relink_supported']==(role=='after')
    if role=='before':
        text=(based/'unsupported-stderr').read_text()
        assert re.search(r'unknown .*(?:flag|unstable option).*relink-only',text,re.I),text
    phase=[]
    for i,(name,h) in enumerate(sorted(terminal['phases'].items()),1):
        path=based/(name+'.json');assert sha(path)==h
        a=read(path); phase.append(a)
        assert name[:2]==f'{i:02d}' and a['phase']==name
        orderset=(a['source'],a['binary_source'],a['asset'])
        if i not in global_inputs:global_inputs[i]=orderset
        assert global_inputs[i]==orderset
        assert a['empty']==(i in (1,4,7,10))
        assert a['raw'] and all(re.fullmatch('[0-9a-f]{64}',v) for v in a['raw'].values())
        has_cached=arm=='after-relink'
        failed=i in (7,8) or i==6 and not has_cached
        assert a['status']==(101 if failed else 0)
        assert a['missing_diagnostic']==failed
        successful_link=not failed and i!=2
        real_link=[j for j in a['jobs'] if j.get('file')=='rust-lld']; assert len(real_link)==int(successful_link)
        assert all(j['exe']==sdk['checked']['lib/rustlib/x86_64-unknown-linux-gnu/bin/rust-lld'] for j in real_link)
        rustcs=[j for j in a['jobs'] if j['kind']=='rustc']
        assert all(j['public_hash'] and not j['incremental'] and j['exe']==terminal['rustc'] for j in rustcs)
        assert sum(j['unit']=='producer' and not j['link_only'] for j in rustcs)==int(i in (1,3,4,6,7,10))
        reader=[j for j in rustcs if j['unit']=='reader']
        expected_full=i!=2 and not (has_cached and i in (3,6))
        assert sum(not j['link_only'] for j in reader)==int(expected_full)
        assert sum(j['link_only'] for j in reader)==int(has_cached and successful_link)
        assert all(o['rustc_unit']=='reader' for o in a['asset_opens'])
        assert bool(a['asset_opens'])==expected_full
        assert all(o['acquired']!=failed and o['missing']==failed for o in a['asset_opens'])
        if not failed:
            expect_native=17 if i in (1,2,9,10) or i==3 and has_cached else 29
            expect_rust=10 if i in (3,4,5) else 6
            assert (a['native'],a['rust'])==(expect_native,expect_rust)
        pub=[v for k,v in a['public_api_files'].items() if k.endswith('/lib-producer.public-api-hash')]
        assert len(pub)==1 and pub[0]['version']==1
        if i==1:producer_pub=pub
        assert pub==producer_pub
        assert all(v['source'] and not v['payload'] for v in a['depinfo'].values())
        assert set((k.endswith('.rlib'),len(v)) for k,v in a['archives'].items())=={(True,64)}
    rows={i+1:v for i,v in enumerate(phase)}
    assert rows[1]['elf']==rows[2]['elf']==rows[9]['elf']==rows[10]['elf']
    assert rows[4]['elf']==rows[5]['elf']
    assert (rows[3]['elf']==rows[4]['elf'])==(arm!='after-relink')
    assert list(rows[1]['archives'].values())!=list(rows[3]['archives'].values())
    assert list(rows[3]['archives'].values())==list(rows[4]['archives'].values())
    assert rows[1]['typed']==[['producer',False],['reader',False]] and rows[2]['typed']==[['producer',True],['reader',True]]
    if arm=='after-relink':
        for i in (1,2,3,4,5,6,9,10):
            obj,=rows[i]['assembly_object']
            assert obj['bytes']==('11' if i in (1,2,3,9,10) else '1d')
        assert rows[1]['assembly_object'][0]['sha256']==rows[3]['assembly_object'][0]['sha256']
        assert rows[4]['assembly_object'][0]['sha256']==rows[5]['assembly_object'][0]['sha256']==rows[6]['assembly_object'][0]['sha256']
    else:assert not any(v['assembly_object'] for v in phase)
    seen.append([arm,rows[3]['native'],rows[6]['status']])
print('Verified 30 native build phases plus one unsupported-switch check.',seen)
