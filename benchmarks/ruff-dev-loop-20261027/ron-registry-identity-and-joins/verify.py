"""Reopen both negative controls, actual package archives, true compiler execs, and Serde output spans."""
from pathlib import Path
import hashlib, io, json, re, tarfile, tomllib

root=Path(__file__).resolve().parent
for line in (root/'SHA256SUMS').read_text().splitlines():
    sha, field=line.split('  ',1); assert hashlib.sha256((root/field).read_bytes()).hexdigest()==sha,field

def files(name):
    with tarfile.open(root/(name+'.tar.gz')) as t:return {m.name:t.extractfile(m).read() for m in t if m.isfile()}
n=files('first-evidence');m=files('managed-and-returned');raw=files('managed-execs');get=lambda d,k:json.loads(d[k]);rows=['initial','repeat','again','clean']
for kind in ('dso','rmeta'):
    a=get(n,'full-identity-'+kind+'/complete.json');ids=get(n,'full-identity-'+kind+'/identities.json');assert set(ids['argv'])=={'hold_direct','hold_probe','hold_shapes','hold_tokens'}
    assert all(args[-1]=='-Zpublic-api-hash=no' for args in ids['argv'].values()) and not ids['marked_depfiles'] and ids['record_has_OBS1']==[False]
    assert a['old']['mtime_ns']==a['replacement']['mtime_ns'] and a['old']['inode']!=a['replacement']['inode'] and a['old']['sha256']!=a['replacement']['sha256']
    assert a['old_token_before_replacement']==17 and any(v['exe']=='rustc' and ('r-xp' if kind=='dso' else 'r--p') in v['permissions'] for v in a['observed_old_maps'])
    r=a['rows']; assert [r[k]['all_fresh'] for k in rows]==[False,True,True,False]
    assert [len([v for v in r[k]['native'] if v.get('crate')=='hold_direct']) for k in rows]==[1,0,0,1]
    if kind=='dso':
        assert [r[k]['value'] for k in rows]==[17,17,17,29] and all(r[k]['exit']==0 for k in rows)
        for field,values in a['sections'].items():assert (values[0]==values[1])==(field!='.text')
    else:
        assert a['rmeta_roots']['old']==a['rmeta_roots']['new'] and [r[k]['exit'] for k in rows]==[0,0,0,101] and any(x['code']=='E0308' for x in r['clean']['diagnostics'])

packages=get(m,'managed/packages.json');lock={p['name']:p for p in tomllib.loads(raw['managed/ws/Cargo.lock'].decode())['package']}; assert set(packages)=={'managed-tokens','managed-macro','managed-reader'}
for pkg,sha in packages.items():
    archive=raw['managed/'+pkg+'-0.1.0.crate'];assert hashlib.sha256(archive).hexdigest()==lock[pkg]['checksum']==sha and lock[pkg]['source'].startswith('registry+')
    with tarfile.open(fileobj=io.BytesIO(archive)) as arc:assert tomllib.loads(arc.extractfile(pkg+'-0.1.0/Cargo.toml').read().decode())['package']['name']==pkg
for mode,q in get(m,'managed/results.json').items():
    assert mode in ('default','full');r=q['phases'];assert q['in_compiler'] and q['mtime_preserved'] and (q['foreign']==(mode=='default')) and q['before']!=q['after']
    assert all((q['sections'][0][s]==q['sections'][1][s])==(s!='.text') for s in ('.rustc','.dynsym','.text'))
    assert [r[k]['value'] for k in rows]==([17,29,29,29] if mode=='default' else [17,17,17,29]);assert [r[k]['cargo']['managed_reader'] for k in rows]==([False]*4 if mode=='default' else [False,True,True,False])
    for k in ('old-precursor','new-precursor',*rows):
        prefix=f'managed/{mode}/{k}/';events=[json.loads(l) for l in raw[prefix+'out'].splitlines()];assert events[-1]=={'reason':'build-finished','success':True}
        a=[x for x in events if x.get('reason')=='compiler-artifact'];assert all(x['package_id'].startswith('registry+') for x in a if x['target']['name'].startswith('managed_'))
        if k not in r:continue
        assert {x['target']['name']:x['fresh'] for x in a}==r[k]['cargo'];args={}
        for f,b in raw.items():
            if not f.startswith(prefix+'exec.'):continue
            for line in b.decode().splitlines():
                if not line.endswith(' = 0') or '"--crate-name",' not in line:continue
                name=re.search(r'"--crate-name", "([^"]+)"',line)[1]
                if name=='___':continue
                args[name]=re.findall(r'"(-Zpublic-api-hash(?:=no|=yes)?)"',line)
                if name=='managed_reader':assert '"managed_macro='+r[k]['macro']+'"' in line
        assert args==r[k]['flags'] and all(v[-1]==('-Zpublic-api-hash=no' if mode=='full' else '-Zpublic-api-hash') for v in args.values())

checks=get(n,'joins/registry.json');assert len(checks)==11 and checks['bitflags-2.13.2']=='3ded4057c258ba199e2d26386d3af3780957ecaee6c4ef4041c6b4b8b97c0b06' and all(re.fullmatch('[0-9a-f]{64}',h) for h in checks.values())
for label in ('ordinary','diagnosed'):
    rs=get(n,'joins/'+label+'/result.json');assert [r['phase'] for r in rs]==['first','repeat'] and all(r['features']==['default','std'] and r['marker'] and not r['fresh'] for r in rs)
    if label=='ordinary':
        for r in rs:
            events=[json.loads(l) for l in raw['joins/ordinary/'+r['phase']+'.out'].splitlines()];ron,=[e for e in events if e.get('reason')=='compiler-artifact' and e['target']['name']=='ron'];assert ron['fresh']==r['fresh'] and ron['features']==r['features']
log=n['joins/diagnosed/joins.log'].decode();blocks=re.findall(r'(?ms)^(JOIN [^\n]+)\n(.*?)^END$',log);assert len(blocks)==136
for start in (0,68):
    seq=blocks[start:start+68];external=[(h,s) for h,s in seq if '/ron-0.12.0/src/' not in h];assert len(external)==3
    for (head,stack),site in zip(external,('ser::serialize_newtype_struct','de::tuple::deserialize_newtype_struct','de::deserialize_seq')):
        assert '/bitflags-2.13.2/src/public.rs" 17:37..17:38 Some("<") 17:90..17:98 Some("Internal")' in head and ' Some(#' in head
        assert 'quote::spanned::join_spans' in stack and ' as syn::spanned::Spanned>::span' in stack and 'serde_derive::'+site in stack
saved=m['return-source/native.tsv'].splitlines();both=m['return-source/repeat.tsv'].splitlines();assert len(saved)==31 and both==saved+saved
for x in saved:assert b'/bitflags-2.13.2/src/public.rs" 17:37..17:98' in x
assert {b'Serializer',b'serialize_newtype_struct',b'Deserialize',b'deserialize',b'SeqAccess',b'next_element'} <= {l.split()[-1] for l in saved}
print('Verified 8 external-input commands, 12 Cargo-managed registry commands, two ordinary ron builds, 136 diagnostic joins, and 31 returned tokens in each expansion.')
