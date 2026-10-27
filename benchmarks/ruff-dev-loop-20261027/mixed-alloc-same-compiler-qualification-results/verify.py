"""Verify every captured workspace and external reader, plus strict cross-history native equivalence."""
import collections
import gzip
import hashlib
import json
import re
import struct
import sys
import tarfile
from pathlib import Path

base=Path(sys.argv[1]) if len(sys.argv)>1 else Path(__file__).resolve().parent
digest=lambda b:hashlib.sha256(b).hexdigest()
def load(p):return json.loads((base/p).read_bytes())
records=load('original-records.json'); ledger=records['records']
forbidden=[b'openai'+b'.'+x for x in [b'org',b'com',b'internal']]+[b'artifactory'+b'.',b'packages.hub.'+b'ace-research',b'authorization:'+b' bearer ',b'github'+b'_pat_',b'-----begin '+b'private key-----',b'-----begin '+b'openssh private key-----',b'gh'+b'p_',b'gh'+b'o_',b'gh'+b's_']
def scan(blob):
    b=blob.lower()
    assert not any(p in b for p in forbidden) and not re.search(rb'(?:AKIA|ASIA)[0-9A-Z]{16}|https?://[^/\s:@]{1,100}:[^/@\s]{2,200}@',blob)
source={}
for f in sorted(base.glob('*.tar.gz')):
    assert f.stat().st_size<8_000_000
    with tarfile.open(f,'r:gz') as t:
        for m in t:
            assert m.isfile() and not m.name.startswith('/') and '..' not in Path(m.name).parts and m.name not in source
            b=t.extractfile(m).read();scan(b);l=ledger[m.name]
            assert digest(b)==l['portable_sha256'] and len(b)==l['portable_bytes']
            if not l['replacements']:assert l['original_sha256']==digest(b) and l['original_bytes']==len(b)
            else:assert records['alias'].encode() in b and b.count(records['alias'].encode())==l['replacements']
            source[m.name]=b
assert set(source)==set(ledger)
for f in base.iterdir():
    if f.is_file() and not f.name.endswith('tar.gz') and f.suffix!='.py':scan(f.read_bytes())
j=lambda n:json.loads(source[n])
artifact=load('native-byte-bindings.json'); refs=load('product-references.json')
counts=load('command-counts.json')
raw_recheck=load('retained-native-recheck.json')
assert len(raw_recheck['ordinary_bridge_rlibs'])==28 and len(raw_recheck['normalized_native_archives'])==36
crates=['ruff_wasm','ty_wasm']
cargo={'B':'dd5cab154b8dcd09ccc2753160d314cade80979b2d055ee66aa9e2217e05e7e1','C':'0f237cc3b506aa90c1224e6ed80f646566b424b78c8d74f288f6523d17fc8aa1'}
driver='63145e253973980f3786ce562b2342d2590b4a783256e4197e8ffacdf7d110fa'
def sections(b):
    assert b[:7]==b'\x7fELF\x02\x01\x01' and struct.unpack_from('<HH',b,16)==(1,62)
    at=struct.unpack_from('<Q',b,40)[0];width,n,names=struct.unpack_from('<HHH',b,58);assert width==64
    sh=[struct.unpack_from('<IIQQQQIIQQ',b,at+i*width) for i in range(n)]
    strs=b[sh[names][4]:sh[names][4]+sh[names][5]]
    return {strs[s[0]:strs.index(0,s[0])].decode():(s,b[s[4]:s[4]+s[5]]) for s in sh}
def member(blob):
    assert blob[:8]==b'!<arch>\n';at=8;out=None
    while at<len(blob):
        n=int(blob[at+48:at+58]);assert blob[at+58:at+60]==b'`\n';start=at+60
        if blob[at:at+16].strip()==b'lib.rmeta/':assert out is None;out=blob[start:start+n]
        at=start+n+n%2
    assert at==len(blob) and out;return out
for k,v in artifact.items():
    hash_=k.split('/')[1];assert v['sha256']==hash_ and v['bytes']>0
    if 'file' in v:
        b=source[v['file']];assert digest(b)==hash_ and len(b)==v['bytes'] and not v['private_strings'] and not v['credential_patterns']
    if k.startswith('archive/'):
        emb=artifact['lib.rmeta.elf/'+v['embedded_elf_sha256']];sep=artifact['standalone.rmeta/'+v['embedded_rmeta_sha256']];actual=artifact['embedded.rmeta/'+v['embedded_rmeta_sha256']]
        assert sep['sha256']==actual['sha256'] and sep['bytes']==actual['bytes']
        if 'file' in emb:
            section,content=sections(source[emb['file']])['.rmeta']
            assert section[2]==0x80000000 and digest(content)==actual['sha256'] and len(content)==actual['bytes']
            if 'file' in sep:assert content==source[sep['file']]==source[actual['file']]
        if 'file' in v:assert digest(member(source[v['file']]))==emb['sha256']
pairs={}
def compare(a,b,attested):
    l,r=a['product'],b['product']
    assert all(l[k]==r[k] for k in ['units','diagnostics','structural_roster','messages'])
    assert l['elf'].keys()==r['elf'].keys()
    different={}
    for k,x in l['elf'].items():
        y=r['elf'][k]
        if x['raw']!=y['raw']:
            assert x['size']==y['size'] and x['content_with_two_wild_fields_masked']==y['content_with_two_wild_fields_masked']
            different[k]=[x,y]
    assert different==attested['allowed_elf_differences'] and attested['raw_equal']==len(l['elf'])-len(different)
    for cr in crates:
        x,y=l['mixed'][cr],r['mixed'][cr]
        assert x['cdylib_elf']['raw']==y['cdylib_elf']['raw']
        for field in ['rmeta_bytes','rmeta_sha256','private_svh','stable_crate_id','public_svh','embedded_object_sha256','root_listing_sha256','exports','zero_byte_allocations','normalized_archive_sha256']:assert x[field]==y[field],(cr,field)
        for z in (x,y):
            native=artifact['archive/'+z['archive']['sha256']]
            assert raw_recheck['normalized_native_archives'][z['archive']['sha256']]==z['normalized_archive_sha256']
            assert native['embedded_elf_sha256']==z['embedded_object_sha256'] and native['embedded_rmeta_sha256']==z['rmeta_sha256'] and native['ordered_symbol_index_digest']==z['archive']['symbol_name_member_ordinal_sha256']
            assert artifact['cdylib/'+z['cdylib_elf']['raw']]['bytes']==z['cdylib_elf']['size']
            txt=source['root/'+z['rmeta_sha256']+'.txt'];assert digest(txt)==z['root_listing_sha256']
            assert f"private hash {z['private_svh']} stable_crate_id StableCrateId({z['stable_crate_id']})".encode() in txt
            assert f"public_hash {z['public_svh']}".encode() in txt and z['zero_byte_allocations']==[1,2,4,8,16,32] and len(z['exports'])>=8
        za,zb=x['archive'],y['archive']
        assert (za['symbol_index_entries'],za['symbol_name_member_ordinal_sha256'],za['referenced_object_member_ordinals'])==(zb['symbol_index_entries'],zb['symbol_name_member_ordinal_sha256'],zb['referenced_object_member_ordinals'])
        objs=list(zip(za['objects'],zb['objects'],strict=True))
        assert all(a[1:]==b[1:] and a[0].rsplit('.',3)[0]==b[0].rsplit('.',3)[0] for a,b in objs)
        assert attested['mixed'][cr]==dict(object_count=len(objs),names_changed=sum(a[0]!=b[0] for a,b in objs),raw_archive_equal=za['sha256']==zb['sha256'],index_entries=za['symbol_index_entries'])
    return {'raw_equal':attested['raw_equal'],'total_elf':len(l['elf']),'mixed':attested['mixed'],'nonidentical_elf':sorted(different)}
complete=j('complete.json');assert complete['timed_samples']==0 and re.fullmatch('[0-9a-f]{64}',complete['native_source_index'])
detail={}; stats={};reader_totals={}
for mode,total in [('build',501),('test',619)]:
    actual={}
    for key,c in counts.items():
        m,arm,phase=key.split('/')
        if m!=mode:continue
        where='receipts/'+key+'/';r=j(where+'receipt.json'); assert r['command']==(['cargo','+ohm','build','--locked','--offline'] if mode=='build' else ['cargo','+ohm','test','--no-run','--locked','--offline']) or (r['command'][:4]==['cargo','+ohm','test','--no-run'] and set(r['command'][4:])=={'--locked','--offline'})
        actual[arm,phase]=r; p=r['processes'];jobs=collections.Counter(i['kind'] for i in p['jobs'])
        rawrows=[json.loads(x) for x in source[where+'stdout'].splitlines() if x]
        built=[o for o in rawrows if o['reason']=='compiler-artifact']
        assert len(built)==c['units']==r['unit_count']==total and sum(not o['fresh'] for o in built)==total-c['fresh'] and c['fresh']==r['fresh_units']
        assert any(o['reason']=='build-finished' and o['success'] for o in rawrows)
        assert r['actual_driver']==driver and r['actual_cargo']==cargo['C' if arm in ('C','forced-C') else 'B'] and r['status']==c['status']==0
        assert c['full']==jobs['full']+jobs['checked-full-fallback'] and c['link_only']==jobs['link-only'] and c['guarded']==jobs['checked-native']
        assert c['native']=={k:len(v) for k,v in p['native'].items()} and c['image_execs']==len(p['images'])
        assert len(set(i['pid'] for i in p['jobs']))==len(p['jobs'])
        if phase.endswith('fresh'):assert c['fresh']==total and not p['jobs'] and not any(c['native'].values())
        if phase in ('first-edit','first-restore','forced-edit','forced-restore'):
            native_expected=8 if mode=='build' else 67
            assert c['native']==dict(cc=native_expected,collect2=native_expected,wild=native_expected)
            assert c['link_only']==(6 if mode=='build' else 62) and c['guarded']==(2 if arm=='C' else 0)
            assert c['full']==(3 if mode=='build' else 6)-(2 if arm=='C' else 0)
            assert set(p['mixed_links'])==set(p['mixed_inputs'])==set(crates)
            procs=j('process-bindings/'+key+'.json');assert procs.keys()==({a['pid'] for a in p['jobs']}|set().union(*p['native'].values()))
            for crate in crates:
                assert p['mixed_inputs'][crate]['argv'][p['mixed_inputs'][crate]['argv'].index('--crate-name')+1]==crate
                assert p['mixed_links'][crate]['argv'] and p['mixed_links'][crate]['retained_archive_inputs']
    specs={'original-cold-C-B':(('C','initial-fresh'),('B','initial-fresh'))}
    for lab in ('edit','restore'):
        specs[lab+'-C-B']=(('C','first-'+lab),('B','first-'+lab))
        specs[lab+'-C-forced-same-state']=(('C','first-'+lab),('forced-C','forced-'+lab))
        for tag in 'BC':specs[lab+'-'+tag+'-independent-full']=((tag,'first-'+lab),('gold-B','initial-fresh') if lab=='edit' else (tag,'initial-fresh'))
    strict=j(mode+'-structural.json');assert strict==complete['completed'][mode]['comparisons'] and complete['completed'][mode]['qualified'] and complete['completed'][mode]['native_rust_reader_gate'] and set(strict)==set(specs)
    pairs[mode]={}
    for name,(a,b) in specs.items():
        assert strict[name]['ok'];pairs[mode][name]=compare(actual[a],actual[b],strict[name]['details'])
    def calc_cold(arm):
        r=actual[arm,'cold'];stdout=source['receipts/'+mode+'/'+arm+'/cold/stdout']
        rows=[json.loads(line) for line in stdout.splitlines()];units=[i for i in rows if i['reason']=='compiler-artifact']
        return rows,units
    _,raw=calc_cold('B');assert not any(i['fresh'] for i in raw)
    proj1=j(mode+'-C-registry.json');assert proj1==j(mode+'-gold-B-registry.json')
    archived=j(mode+'-verified-crate-archives.json');overview=j(mode+'-registry-overview.json')
    assert set(overview['registry'].values())==set(archived) and not overview['registry'].keys()&overview['excluded'].keys()
    assert all((i.get('independent_inode') and re.fullmatch('[0-9a-f]{64}',i['sha256'])) or ('link' in i and not i['link'].startswith('/')) for i in proj1.values())
    cmds=j(mode+'-registry-source-commands.json');assert len(cmds['compilation'])>300
    for arm in ('C','gold-B'):
        _,rows=calc_cold(arm)
        assert all(i['fresh']==i['package_id'].startswith('registry+') for i in rows)
        cold=j(mode+'-'+arm+'-cold-oracle.json')
        assert cold['fresh_registry']==sum(i['fresh'] for i in rows) and cold['workspace_cold']==total-cold['fresh_registry']
        assert {v['sha256'] for k,v in proj1.items() if '/get-size-derive2/' in k and k.endswith('.so')}=={cold['plugin']}
    clone=j('cloned-artifacts-'+mode+'.json');assert len(clone)>=total and all(i['different_inodes'] for i in clone.values())
    detail[mode]=dict(artifact_records=total,checked_registry_archives=len(archived),projected_files=len(proj1),cloned_outputs=len(clone),cold=cold)
    reader_totals[mode]={}
    for lab,names,n in [('edit',['B','C','forced-C','gold-B'],40),('restore',['B','C','forced-C'],24)]:
        checks=j('readers-'+mode+'-'+lab+'.json');assert len(checks)==n
        expect={(cr,a,st,origin) for cr in crates for a in ('bridge','caller') for st in names for origin in (['self'] if a=='bridge' else names)}
        seen=set()
        for row in checks:
            c,a,st,origin=[row[k] for k in ('crate','action','state','bridge_from')]
            key=(c,a,st,origin);assert key not in seen;seen.add(key);d=row['receipt']+'/'
            argv=j(d+'receipt/argv.json');assert argv[:2]==['rustc','+ohm'] and not any('public-api-hash' in arg for arg in argv)
            arg=argv[argv.index('--extern')+1]
            assert arg.startswith((c+'=') if a=='bridge' else 'ordinary_bridge=')
            assert row['wrapper']==row['rustc']==j(d+'receipt/rustc-status.json')['rustc_status']==0
            br=j(d+'receipt/bridge.json');assert br['public_hash_opt_in'] is False and br['action']==a and br['crate']==c
            assert row['runtime']==br['runtime']==(None if a=='bridge' else ('0.17.0' if c=='ruff_wasm' else '93526150d'))
            rolephase='initial-fresh' if st=='gold-B' else ('forced-' if st=='forced-C' else 'first-')+lab
            assert br['current_rlib_sha256']==actual[st,rolephase]['product']['mixed'][c]['archive']['sha256']
            assert 'reader-output/'+br['result_sha256'] in artifact
            if a=='bridge':assert raw_recheck['ordinary_bridge_rlibs'][d+'libordinary_bridge.rlib']==br['result_sha256']
            else:
                from_path=next(x['receipt'] for x in checks if x['action']=='bridge' and x['state']==origin and x['crate']==c)
                assert raw_recheck['ordinary_bridge_rlibs'][from_path+'/libordinary_bridge.rlib']==j(from_path+'/receipt/bridge.json')['result_sha256']
        assert seen==expect;reader_totals[mode][lab]={'actions':n,'external_callers':2*len(names)**2,'independent_bridges':2*len(names)}
result={'zero_timed_samples':0,'verified_workspace_commands':len(counts),'reader_actions':reader_totals,'verified_registries':detail,'strict_comparisons':pairs,'native_input_files':len(artifact),'public_metadata_files':sum('file' in v for k,v in artifact.items() if k.split('/')[0] in ('standalone.rmeta','lib.rmeta.elf','embedded.rmeta')),'withheld_binary_kinds':dict(collections.Counter(k.split('/')[0] for k,v in artifact.items() if v.get('private_strings') or v.get('credential_patterns'))),'original_member_hashes':len(ledger),'text_records_aliased':sum(v['replacements']>0 for v in ledger.values())}
print(json.dumps(result,sort_keys=True,indent=2))
