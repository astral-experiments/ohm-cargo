"""Verify the distributed -15 binary, all 9 builds and every ordinary Rust/native reader."""
from pathlib import Path
import hashlib,json,re
r=Path(__file__).parent.resolve();e=r/'evidence'
def h(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def read(path):return json.loads(path.read_bytes())
provenance=read(r/'provenance.json');trans=read(r/'transferred.json');sdk=read(r/'installed.json');m=read(r/'manifest.json')
assert provenance['tag']==m['release']['toolchain_name']=='ohm-1.99.0-15'
assert provenance['asset']['digest']=='sha256:'+sdk['package_sha256']=='sha256:'+trans['sha256']
assert provenance['asset']['size']==trans['bytes']==sdk['package_bytes']==359640412
for tool in ('cargo','rustc'):
    pin=m['sources']['cargo' if tool=='cargo' else 'rust']['revision'];assert 'commit-hash: '+pin in sdk['versions'][tool]
assert h(r/'repro.py')==sdk['fixture_sha256']
record=read(e/'tools.json')
assert all(record[k]==sdk[v] for k,v in [('cargo_sha256','cargo'),('driver_sha256','driver'),('frontend_sha256','frontend')])
results=read(e/'results.json');done=read(e/'complete.json')
assert done['results_sha256']==h(e/'results.json') and done['timings']==0 and set(results)=={'parse','programmatic','legacy'}
apps=read(e/'native-executables.json');counts=[0,0,0,0]
for variant,g in results.items():
    q=e/variant
    before=(q/'unit-before.rs').read_text();after=(q/'unit-after.rs').read_text();assert before.count('{ 7 }')==1 and before.replace('{ 7 }','{ 8 }')==after and 'include!("late.rs")' in after
    for suffix in ('training','warm','empty'):
        build=q/suffix
        expected=['cargo','+ohm',*(['-Zohm-defaults=no'] if variant=='legacy' else []),'build','-p','test_unit','--locked','--offline','--message-format=json']
        assert read(build/'argv.json')==expected and read(build/'status.json')['returncode']==0
        rows=[json.loads(l) for l in (build/'stdout').read_text().splitlines() if l]
        assert rows[-1]=={'reason':'build-finished','success':True}
        actual=read(build/'result.json');assert actual['rmeta_sha256']==h(build/'raw.rmeta') and not actual['unit_fresh']['test_unit']
        assert read(build/'header/argv.json')[:3]==['rustc','+ohm','-Zls=root'] and read(build/'header/status.json')['returncode']==0
        header=(build/'header/stdout').read_text();assert 'private hash '+actual['header']['private'] in header and 'public_hash '+actual['header']['public'] in header
        if suffix!='training':assert g['builds'][suffix]==actual
        counts[0]+=1
    a,b=(g['builds'][s] for s in ('warm','empty'));assert a['proc_macro_sha256']==b['proc_macro_sha256'] and a['header']['stable']==b['header']['stable']
    assert (a['header']['private']!=b['header']['private'])==(variant=='parse')
    for s in ('warm','empty'):
        bridge=q/('bridge-'+s);args=read(bridge/'argv.json');assert args[:2]==['rustc','+ohm'] and read(bridge/'status.json')['returncode']==0 and (bridge/'libbridge.rlib').is_file();counts[1]+=1
        for t in ('warm','empty'):
            call=q/(s+'-caller-'+t);row=g['readers'][s+'/from-'+t];status=read(call/'status.json')['returncode']
            assert row['bridge_sha256']==h(q/('bridge-'+t)/'libbridge.rlib') and read(call/'argv.json')[:2]==['rustc','+ohm'] and row['diagnostics_sha256']==h(call/'stderr') and row['compiler_status']==status
            assert (status==1)==(variant=='parse' and s!=t);counts[2]+=1
            if status:
                assert 'error[E0460]' in (call/'stderr').read_text() and row['runtime'] is None
            else:
                n=call/'native';assert read(n/'status.json')['returncode']==0 and len(read(n/'argv.json'))==1 and not (n/'stderr').read_bytes()
                app=apps[(call/'app').relative_to(e).as_posix()];assert app['bytes']>0 and len(app['sha256'])==64
                printed=(n/'stdout').read_text().strip();assert printed==row['runtime'];counts[3]+=1
                pos=re.fullmatch(r'8:#0 bytes\((\d+)\.\.(\d+)\)',printed);assert pos and int(pos[2])-int(pos[1])==10
    pair=[g['readers'][s+'/from-'+s]['runtime'] for s in ('warm','empty')]
    assert (pair[0]!=pair[1])==(variant=='parse')
assert counts==[9,6,12,10] and len(apps)==10
print('Verified the official -15 package, nine Cargo builds, six Rust bridge builds, twelve ordinary Rust callers and ten actual native executions.')
