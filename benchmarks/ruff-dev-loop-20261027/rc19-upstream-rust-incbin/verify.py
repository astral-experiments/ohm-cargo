#!/usr/bin/env python3
"""Verify the upstream 1.99.1 native archive comparison, inputs and physical reader commitments."""
import argparse,base64,copy,gzip,hashlib,json,re,tomllib
from pathlib import Path
D=Path(__file__).resolve().parent
def h(b):return hashlib.sha256(b).hexdigest()
def check(d):
    assert d['terminal_sha256']=='c4bb273300897f8df0667f17f9418559c5527877f28f1b0db1448dd2e4796eb7'
    p=json.loads((D/'toolchain.json').read_bytes())
    assert p['commit']==p['tag_commit']=='58cf8f9c35b355199727627d07ae34a4e2846d67'
    assert p['tag_object']=='213cfbe66a6da4e4b41bde365643286371af6e5a' and p['release']=='1.99.1'
    raw=gzip.decompress((D/'official-channel.toml.gz').read_bytes())
    assert h(raw)==p['official_manifest_sha256']=='fb152be80975c194aa5fc684b2aec3a6e14e2b855efe2faa4e5f8ae6e590f463'
    off=tomllib.loads(raw.decode())
    assert off['date']==p['date']=='2026-10-15'
    for k in ('cargo','rustc','rust-std'):
        a=off['pkg'][k];v=p['components'][k];assert a['git_commit_hash']==v['git_commit'] and a['version']==v['version']
        assert all(a['target'][p['target']][t]==v[t] for t in ('hash','url','xz_hash','xz_url'))
    assert p['cargo_sha256']=='a670e02cfa39ac2e53f77a2d911ca1fc9e2c479b0603ec956625be1daf24e3af' and p['rustc_sha256']=='b53b780f77f952062f8ca8a3b70aef2390b1e45ad91939be94afdc9543026853'
    for name in ['rustc','cargo']:
        v=(D/(name+'-version.txt')).read_text()
        source_commit=p['commit'] if name=='rustc' else '5f94df4789f005f9a352888e8355ffc645b7ed0e'
        assert source_commit in v and source_commit[:9] in p['components'][name]['version']
        assert p['components'][name]['git_commit']==p['commit'] and '1.99.1' in v and 'ohm' not in v.lower()
    mf=(D/'fixture/consumer/Cargo.toml').read_bytes();edit=mf.replace(b'\ntest = false\n',b'\n')
    assert mf!=edit
    phases=['initial','untouched','flag-edit','edit-repeat','empty-edited','restored','final-repeat'];families=['incremental','nonincremental']
    rows=d['rows'];assert len(rows)==len(set((r['family'],r['phase']) for r in rows))==14
    assert set((r['family'],r['phase']) for r in rows)=={(a,b) for a in families for b in phases}
    for r in rows:
        phase=r['phase'];inc=r['family']=='incremental';edited=phase in ['flag-edit','edit-repeat','empty-edited']
        actual=edit if edited else mf;expect=17 if not edited or inc and phase!='empty-edited' else 29
        fresh=phase in ['untouched','edit-repeat','final-repeat']
        assert r['commit']==p['commit'] and len(r['rustc_argv'])==int(not fresh) and r['fresh']==fresh
        assert r['target_test']==edited and h(actual)==r['manifest_sha256']
        assert r['program']==expect and r['stdout']==f'{expect}\n' and r['raw']['program.stdout']==h(r['stdout'].encode())
        assert r['actual_member'].endswith('.o') and re.fullmatch('[0-9a-f]{64}',r['object_sha256'])
        assert r['actual_native_archive_sha256']==r['raw']['libmanifest_case.rlib'] and r['actual_program_sha256']==r['raw']['reader']
        data=base64.b64decode(r['object_section_base64'],validate=True)
        assert data==(mf if expect==17 else edit) and h(data)==r['embedded_sha256']==r['raw']['embedded-manifest.toml']
        assert any(x.startswith('events.') for x in r['raw']) and all(re.fullmatch('[0-9a-f]{64}',x) for x in r['raw'].values())
        for a in r['rustc_argv']:assert a[a.index('--crate-name')+1]=='manifest_case' and inc==any(x.startswith(('-Cincremental=','incremental=')) for x in a)
        assert r['dep_info'] and all(v['matches_retained_file'] for v in r['dep_info'])
        rustd=[v for v in r['dep_info'] if not v['name'].endswith('/libmanifest_case.d')]
        assert rustd and all('Cargo.toml' not in v['body'] and 'consumer/src/lib.rs' in v['body'] for v in rustd)
def main():
    p=argparse.ArgumentParser();p.add_argument('--mutations',action='store_true');opts=p.parse_args()
    files={f.relative_to(D).as_posix():h(f.read_bytes()) for f in D.rglob('*') if f.is_file() and f.name!='SHA256SUMS' and '__pycache__' not in f.parts}
    refs={n:v for v,n in [line.split('  ',1) for line in (D/'SHA256SUMS').read_text().splitlines()]};assert refs==files
    obs=json.loads(gzip.decompress((D/'observations.json.gz').read_bytes()));check(obs)
    if opts.mutations:
        for field,value in [('program',29),('object_section_base64','V1JPTkc='),('fresh',True)]:
            bad=copy.deepcopy(obs);next(r for r in bad['rows'] if (r['family'],r['phase'])==('incremental','flag-edit'))[field]=value
            try:check(bad)
            except AssertionError:pass
            else:raise AssertionError('mutation accepted')
    print('Official Rust/Cargo 1.99.1 identifiers, fourteen ordinary programs, both cache settings, embedded object bytes and dep-info verified.')
if __name__=='__main__':main()
