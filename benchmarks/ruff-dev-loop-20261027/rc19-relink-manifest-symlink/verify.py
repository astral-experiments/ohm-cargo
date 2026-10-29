"""Verify the closed seven-state native comparison and the two standalone replays."""

import gzip
import hashlib
import json
import re
from pathlib import Path


def verify(doc):
    cases={
        'ordinary/cold':17,'ordinary/observer-after-delete':29,'ordinary/preexisting-before':31,
        'post-rustc/cold':17,'post-rustc/after':29,'explicit-no/cold-after':29,'defaults-off/cold-after':29}
    subjects={
        'package19':'789c2f116732ed642565d0f92c500838f8cd53664fbe60f205a5621c43cbecf1',
        'candidate282':'749cde35ef1f4fb78954d7110ee4ee9a8271159aec9f9f67390fcb1e5419b3b6',
        'fixed':'5cc0517d944c86d10dd8595ee8941f33ad5b15183fd56493cb799e3222b44021'}
    expected_archives={'sentinel-v2':'eeeb6fa4d71a3df3e3b00101badd059df289f92ad72fe1d87439f9e500f47a92','sentinel-v3':'4753f4fb6c8e730471ff236a010230cc1a1d7fdc5ddb8396b8c4c43141852ece','sentinel-green-v1':'c53feaa932ca797f9401dfb7661f21aca02cef3d6ef429db9c65613bcdf7733a'}
    assert doc['archives']==expected_archives and set(doc['subjects'])==set(subjects)
    assert doc['diagnostic_first_archive']=='a4823a96e5af8ac2ce6749748db3853786098f4a0c0b5c458c42f0c836554bf3'
    assert doc['subjects']['package19']['archive']=='ef21d83519bc376479811a7e01fa5ac8915ac0a500c6859bc22a1e0b4913d812'
    assert doc['subjects']['fixed']['source']=='5394ce8817e224971230b80a9066cc28d504ff94'
    assert all(doc['subjects']['fixed'][x]==doc['subjects']['candidate282'][x] for x in ('rustc','driver','wild'))
    expected={f'{arm}/{case}' for arm in subjects for case in cases};assert set(doc['rows'])==expected
    hash_pattern=re.compile('[0-9a-f]{64}').fullmatch
    total=0
    for k,r in doc['rows'].items():
        arm,case=k.split('/',1); group=case.split('/',1)[0]
        assert doc['subjects'][arm]['cargo']==subjects[arm] and r['arm']==arm
        assert r['cargo_exit']==0 and r['program']==cases[case] and r['uid']==1000
        assert r['wrapped_rustc']==(group!='ordinary') and r['execs']['rustc']==1 and r['execs'].get('after-real-rustc',0)==r['wrapped_rustc']
        if group=='defaults-off' and arm=='package19':assert r['execs']['ld.lld']==r['execs']['rust-lld']==1
        elif group=='defaults-off':assert r['execs']['ld']==1
        else:assert r['execs']['ld.bfd']==1
        flags={'explicit-no':['-Zrelink-only=no'],'defaults-off':['-Zohm-defaults=no']}.get(group,[]);assert r['flags']==flags
        active=case in ('ordinary/observer-after-delete','post-rustc/after');corrupt=active and arm!='fixed'
        assert r['sentinel_replaced']==r['inode_changed']==corrupt and r['watcher_received_in_delete']==(case=='ordinary/observer-after-delete')
        assert (r['sentinel_before_sha256']!=r['sentinel_after_sha256'])==corrupt
        assert r['manifest_after']==('symlink' if corrupt or flags else 'regular')
        for field in ('elf_sha256','stdout','stderr','manifest_sha256','sentinel_before_sha256','sentinel_after_sha256','raw_record_sha256'):
            assert hash_pattern(r[field])
        assert r['kernel_stream_sha256'] and all(hash_pattern(v) for v in r['kernel_stream_sha256']);total+=len(r['kernel_stream_sha256'])
        events=[x['action']for x in r['kernel']];assert all(hash_pattern(x['raw_line_sha256'])for x in r['kernel'])
        if corrupt:
            assert r['sentinel_after_bytes']>r['sentinel_before_bytes'] and r['sentinel_after_sha256']==r['manifest_sha256']
            assert events[-2:]==['readlink_manifest_to_sentinel','replace_sentinel'] and r['kernel'][-2]['actor']==r['kernel'][-1]['actor']
        else:
            assert r['sentinel_after_bytes']==r['sentinel_before_bytes'] and 'replace_sentinel' not in events and 'readlink_manifest_to_sentinel' not in events
            if not flags:assert events[-1]=='replace_manifest'
        if case in ('ordinary/observer-after-delete','ordinary/preexisting-before'):assert events[0]=='unlink_manifest'
        if group=='post-rustc' and active or flags:assert 'install_link_to_sentinel' in events
        if arm=='fixed':assert r['elf_sha256']==doc['rows']['candidate282/'+case]['elf_sha256']
    assert sum(r['sentinel_replaced'] for r in doc['rows'].values())==4
    for label,expect in [('portable19',True),('portable-fixed',False)]:
        s=doc['standalone_no_wrapper'][label];assert s['exit']==0 and s['stderr_sha256']==hashlib.sha256(b'').hexdigest()
        assert [(r['phase'],r['program'])for r in s['rows']]==[('cold',17),('during',29),('before',31)]
        assert [r['sentinel_replaced']for r in s['rows']]==[False,expect,False]
        for r in s['rows']:
            assert (r['sentinel_sha256_after']!=r['sentinel_sha256_before'])==r['sentinel_replaced'] and r['manifest_is_symlink']==r['sentinel_replaced']
    return total


if __name__=='__main__':
    p=Path(__file__).resolve().parent
    files={f.name for f in p.iterdir() if f.is_file() and f.name!='SHA256SUMS'}
    sums={}
    for line in (p/'SHA256SUMS').read_text().splitlines():
        h,name=line.split('  ',1);assert name in files and name not in sums;sums[name]=h
    assert set(sums)==files and all(hashlib.sha256((p/k).read_bytes()).hexdigest()==v for k,v in sums.items())
    data=gzip.decompress((p/'verdicts.json.gz').read_bytes());j=json.loads(data)
    n=verify(j)
    # A stale result, changed syscall or falsely claimed correct program must be rejected.
    for arm,key,field,replacement in [('fixed','ordinary/observer-after-delete','sentinel_replaced',True),('package19','ordinary/observer-after-delete','wrapped_rustc',True),('fixed','ordinary/preexisting-before','program',29),('candidate282','post-rustc/after','kernel',[])]:
        ch=json.loads(data);ch['rows'][arm+'/'+key][field]=replacement
        try:verify(ch)
        except (IndexError,KeyError,AssertionError):continue
        raise RuntimeError(f'accepted mutation {arm}/{key} {field}')
    print(f'21 traced builds, {n} original kernel streams, 7 matched executables, 6 independent bare-Cargo commands and 4 rejected mutations')
