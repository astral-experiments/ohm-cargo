"""Cross-check native release subjects, actual invocations, outputs and archive-member commitments."""
from pathlib import Path
import gzip,json
p=Path(__file__).resolve().parent
def get(n):return json.loads(gzip.decompress((p/(n+'.json.gz')).read_bytes()))
w=get('whole');s=get('small');m=get('archive-members')
assert set(w['histories'])==set('ABC') and set(s)=={'PP','PA','AP','AA'}
for arm,h in w['histories'].items():
    for i,phase in enumerate(('cold','first','settled')):
        a=h['phases'][phase];cmd=a['command'];q=cmd['processes'];phys=a['full_physical']
        assert len(a['unit_roster'])==619 and len(a['product_ids'])==len(w['native'][arm+':'+phase])==110
        assert cmd['fresh']==(0,(619 if arm=='C' else 563),619)[i]
        assert sum(mode=='full' for _,mode in phys['rustc'])==q['full'] and sum(mode=='link-only' for _,mode in phys['rustc'])==q['relink']
        assert sum(v[1] for v in phys['native_links'])==q['wild'] and sum(not v[1] for v in phys['native_links'])==q['system']
        if i==0:assert q['full']==636 and q['relink']==0 and q['wild'] in (200,201) and q['system']==62
        if i==1 and arm!='C':assert q['full']==1 and q['relink']==q['wild']==50 and ['ron','full'] in phys['rustc']
        if i==2 or i==1 and arm=='C':assert q['full']==q['relink']==q['wild']==q['system']==q['probe']==0
        proof=a['proof'];assert len(proof['physical_inputs'])==cmd['checksums']==(45 if i>0 or arm=='C' else 0)
        assert proof['depinfo_sha256']==cmd['ron_depinfo'] and proof['encoded_sha256']==cmd['ron_fingerprint'] and len(proof['seal_blake3'])==64
    assert h['ordinary_native_oracles']==w['histories']['C']['ordinary_native_oracles'] and h['ordinary_native_oracles']['passed']
    assert w['native'][arm+':first']==w['native'][arm+':settled']
assert w['native']['C:cold']==w['native']['C:first'] and w['native']['B:cold']==w['native']['C:cold']
pairs={(r['a'],r['b']):r for r in m['pairs']}
for arm in 'AB':
    z=pairs[arm+'-cold',arm+'-first'];assert z['common_members']==12 and not z['a_only_members'] and not z['b_only_members'] and z['changed_common_members']==['lib.rmeta'] and z['source_digests_found']==[0,17]
assert pairs['B-cold','C-cold']['raw_metadata_equal'] and pairs['B-cold','C-cold']['raw_archive_equal'] and pairs['C-cold','C-first']['raw_archive_equal']
for arm,b in s.items():
    assert len(b['tiny'])==3 and len(b['held'])==11 and b['tiny']['unchanged-1']['fresh']==(23 if arm=='PP' else 16)
    for name,row in b['held'].items():assert row['runtime']==s['PP']['held'][name]['runtime'] and row['native']==s['PP']['held'][name]['native']
e=w['additional_controls'];assert e['run_make']['returncode']==0 and e['run_make']['driver']==w['histories']['C']['rust']
assert len(e['hot_swap'])==9 and all(v['returncode']==0 for v in e['hot_swap'].values())
fifo=e['no_writer_fifo'];assert fifo['no_writer_ever'] and not fifo['timed_out_in_open'] and fifo['command_returncode']==101 and fifo['programs_equal'] and all(x & 0x800 for x in fifo['open_flags'])
for arm in ['stock','current']:
    x=e[arm];assert x['missing']['rc']==101 and all(v['rc']==0 for n,v in x.items() if n!='missing')
    for n in ['workspace-wrapper','custom-rustc-arg','defaults-off']:assert not any('-Zohm-observer-dep-info' in v for v in x[n]['compiler_flags'])
checks=e['physical_checksums'];assert checks['PP']==checks['AP'] and checks['PA']==checks['AA'] and checks['PP']['entries']==45 and checks['PP']['sealed_bytes']==12101
print('Verified 9 whole-workspace phases, 56 small commands, 9 tool downgrades/returns, FIFO and native archive/metadata controls.')
