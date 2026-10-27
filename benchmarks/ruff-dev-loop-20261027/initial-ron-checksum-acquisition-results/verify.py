"""Verify the complete post-cold dispatch and native artifacts from the accompanying receipts."""
import json,hashlib
from pathlib import Path
D=Path(__file__).resolve().parent; j=json.loads((D/'observations.json').read_bytes());w=json.loads((D/'native-one.json').read_bytes());assert set(j)=={'tiny-default','tiny-trusted','whole-default','whole-trusted'}
for arm,ph in j.items():
    a,b,c=(ph[n] for n in ('cold','unchanged-1','unchanged-2'));whole=arm.startswith('whole');n=619 if whole else 23;fan=50 if whole else 5
    assert [x['units'] for x in (a,b,c)]==[n]*3 and [x['fresh'] for x in (a,b,c)]==[0,n-(56 if whole else 7),n]
    assert [x['test_executables'] for x in (a,b,c)]==[102 if whole else 5]*3 and [len(x['native']) for x in (a,b,c)]==[110 if whole else 5]*3
    assert len(a['rustc_jobs']['full'])==(636 if whole else 27) and not a['rustc_jobs']['link-only'] and len(a['bundled_wild_outputs'])==(201 if whole else 15)
    assert b['rustc_jobs']['full']==['ron'] and len(b['rustc_jobs']['link-only'])==len(b['bundled_wild_outputs'])==fan and not c['rustc_jobs']['full'] and not c['rustc_jobs']['link-only'] and not c['bundled_wild_outputs']
    assert a['ron']['physical']==b['ron']['physical']==1 and c['ron']['physical']==0 and a['ron']['flags']==[] and b['ron']['flags']==['-Zbinary-dep-depinfo','-Zchecksum-hash-algorithm=blake3']
    assert a['ron']['checksum_records']==0 and b['ron']['checksum_records']==c['ron']['checksum_records']>0 and b['ron']['dirty_reasons'][0]['basename']=='ohm-foreign-span-bytes'
    assert a['ron']['fingerprint_json_sha256']==b['ron']['fingerprint_json_sha256']==c['ron']['fingerprint_json_sha256'];assert a['ron']['files']['dep-lib-ron']!=b['ron']['files']['dep-lib-ron']==c['ron']['files']['dep-lib-ron'] and any(a['ron']['files'][k]!=b['ron']['files'][k] for k in a['ron']['files'] if k.endswith('.rmeta'))
    assert a['messages_sha256']==b['messages_sha256']==c['messages_sha256'] and b['native']==c['native'] and not c['changed_native']
    if whole:
        delta={k for k in a['native'] if a['native'][k]!=b['native'][k]};assert len(delta)==1;name,=delta;assert name.endswith('/ty_python_semantic-a879b0690f634244') and a['native'][name]==w['cold_sha'] and b['native'][name]==w['trained_sha'];assert b['ron']['checksum_records']==45
    else:assert a['native']==b['native']
    print(arm,'cold/first/second(s)',*[round(x['elapsed_ns']/1e9,3) for x in (a,b,c)],'cold+first',round((a['elapsed_ns']+b['elapsed_ns'])/1e9,3),'first rustc/relink/bundled Wild',1,fan,fan)
assert w['bytes_old']==w['bytes_new']==178680456 and w['different_bytes']==33 and len(w['diff_hunks_or_first_200_bytes'])==33;assert w['cold']['raw']==w['cold_sha'] and w['trained']['raw']==w['trained_sha'];assert w['cold']['content_with_two_wild_fields_masked']==w['trained']['content_with_two_wild_fields_masked'];assert [w['cold']['rodata_entsize'],w['trained']['rodata_entsize']]==[8,0];assert set(k for k in w['cold']['section_hashes'] if w['cold']['section_hashes'][k]!=w['trained']['section_hashes'][k])=={'.rodata','.note.gnu.build-id'}
print('Passed all 12 actual Cargo unit/process rosters, complete hashes, observer flags and sole raw ELF difference.')
