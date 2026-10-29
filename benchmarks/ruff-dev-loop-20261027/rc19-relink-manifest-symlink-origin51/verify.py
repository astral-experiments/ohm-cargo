"""Verify portable historical facts against every committed phase and observed rename/exec."""
from pathlib import Path
import gzip, hashlib, json, sys

def check(series):
    commands=0;traced=0;verdicts={}
    for role,case in series.items():
        settings=case['terminal']
        findings=case['observations']
        assert len(findings) in (6,7)
        enabled=settings['mode']=='head-relink'
        assert settings['cargo_commit'].startswith('caac2566f0' if settings['mode'].startswith('head') else '30004d93bd')
        assert settings['no_wrapper'] and bool(settings['traced'])==all('raw_trace_files' in r for r in findings)
        assert all(r['returncode']==0 and r['program']==[17,18,19,31,31,17,20][i] and r['argv']==settings['argv'] for i,r in enumerate(findings))
        assert ('-Zrelink-only' in settings['argv'])==(enabled or settings['mode']=='head-flag-only')
        assert any('public-api-hash' in a for a in settings['argv'])==(enabled or settings['mode'].endswith('public'))
        result={}
        for row in findings:
            stage=row['phase'][:2]
            operations=row.get('manifest_operations',[])
            is_full=stage in ('01','02','03','06','07')
            is_refresh=stage=='04'
            victim=row.get('victim')
            changes=enabled and stage in ('02','04','07')
            if victim:
                assert victim['changed']==changes and (victim['inode_before']!=victim['inode_after'])==changes
                if changes:
                    assert row['manifest_symlink'] and victim['new_manifest_version']==3 and victim['object_count']>0
                    assert victim['symlink_reaches_victim']
                if stage=='07':assert victim['before'] is None and bool(victim['after'])==changes
                result[stage]=changes
            if stage=='01':assert row['manifest_regular']==enabled
            if stage=='02' and enabled:assert row['watch']['mask']&512
            if stage=='03' and enabled:assert row['manifest_regular'] and not row['manifest_symlink']
            if stage=='05':assert all(t[1] for t in row['typed'])
            if not settings['traced']:continue
            traced+=1
            rust=[j for j in row['execs'] if j['kind']=='rustc']
            assert all(j['binary']=='e173035a5dd384e17ca6a178e1987a0a746260c3669459cfab3af580880927ba' for j in rust)
            assert all(j['public_hash']==any('public-api-hash' in a for a in settings['argv']) for j in rust)
            main=[j for j in rust if j['unit']=='probe']
            if stage=='05':assert not row['execs'];continue
            if is_refresh and enabled:assert len(main)==1 and main[0]['link_only'] and any(j['unit']=='producer' and not j['link_only'] for j in rust)
            elif is_full and enabled:assert len(main)==2 and sum(j['link_only'] for j in main)==1
            else:assert len(main)==1 and not main[0]['link_only']
            links=[j['executable'] for j in row['execs'] if j['kind']=='link']
            assert set(links)=={'cc','collect2','ld.lld','rust-lld'} and len(links)==4
            renames=[o for o in operations if o['call'].startswith('rename') and o['result']=='0']
            unlinks=[o for o in operations if o['call'].startswith('unlink') and o['result']=='0' and 'manifest' in o['paths']]
            if changes:
                assert len([o for o in renames if 'victim' in o['paths']])==1
                if stage=='02':assert len(unlinks)==1 and float(unlinks[0]['time'])<float(renames[-1]['time'])
                if stage in ('04','07'):assert not unlinks
            elif enabled and stage=='03':assert len(unlinks)==1 and [o for o in renames if 'manifest' in o['paths']]
            elif not enabled:assert not renames and not unlinks
        verdicts[role]=result;commands+=len(findings)
    assert commands==44 and traced==38
    return {'ordinary_builds':commands,'traced_builds':traced,'without_external_trace':commands-traced,'cases':verdicts}

if __name__=='__main__':
    p=Path(__file__).resolve().parent
    for line in (p/'SHA256SUMS').read_text().splitlines():
        h,n=line.split('  ',1);assert hashlib.sha256((p/n).read_bytes()).hexdigest()==h,n
    x=json.loads(gzip.decompress((p/'observations.json.gz').read_bytes()))
    assert check(x)==json.loads((p/'result.json').read_bytes())
    print('44 ordinary historical builds verified, including 38 traced commands and all sentinel dispositions')
