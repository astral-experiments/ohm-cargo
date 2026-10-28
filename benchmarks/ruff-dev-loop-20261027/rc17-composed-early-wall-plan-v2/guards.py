"""Review the exact native runs and commit the finite raw per-product references."""
import collections
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import stat
import subprocess
from elf import fingerprint

HERE = Path(__file__).resolve().parent
BASE = Path('/mnt/devbox-scratch/dev-user/ohm-combined-prs-20261028')
P = json.loads((HERE/'plan.json').read_bytes())
ROLES = P['subjects']


def read(path):
    return json.loads(path.read_bytes())


def sha(path):
    with path.open('rb') as fd:
        return hashlib.file_digest(fd,'sha256').hexdigest()


def digest(obj):
    return hashlib.sha256(json.dumps(obj,sort_keys=True,separators=(',',':')).encode()).hexdigest()


def save(path,obj):
    tmp=path.with_suffix('.pending')
    with tmp.open('x') as out:
        json.dump(obj,out,sort_keys=True,indent=2)
        out.write('\n')
    os.replace(tmp,path)


def manifest(root):
    subprocess.run(['sha256sum','--quiet','-c','SHA256SUMS'],cwd=root,check=True)
    return sha(root/'SHA256SUMS')


def worker():
    root=BASE/'protocol-v3'
    assert manifest(root)==P['native_manifest'] and sha(root/'ruff_worker.py')==P['native_worker']
    assert read(root/'registered.json')=={'ref':P['native_commit'],'manifest':P['native_manifest']}
    spec=importlib.util.spec_from_file_location('qualified_rc17',root/'ruff_worker.py')
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def summary(products):
    return digest([products['units'], products['roster'], products['exes'], products['e2e'],
                   products['ty_server'], sorted(products['diagnostics'],key=digest)])


def cargo_roster(events,products):
    assert events[-1]=={'reason':'build-finished','success':True}
    arts=[r for r in events if r['reason']=='compiler-artifact']
    ws=[r for r in arts if r['package_id'].startswith('path+')]
    schema=('package_id','manifest_path','target','profile','features','filenames','executable')
    encoded=sorted(json.dumps({k:r[k] for k in schema},sort_keys=True) for r in arts)
    assert len(arts)==619 and digest(encoded)==products['roster']
    assert sum(r['fresh'] for r in arts)==products['fresh']
    exes={r['executable'] for r in ws if r['executable']}
    assert len(exes)==102 and exes==set(products['exes']) and exes<=set(products['native'])
    assert collections.Counter(bool(r['profile']['test']) for r in ws if r['executable'])=={True:84,False:18}
    filenames={f for r in ws for f in r['filenames'] if Path(f).suffix in ('','.so')}
    assert set(products['native'])<=filenames
    diags=[[r['package_id'],r['message']] for r in events if r['reason']=='compiler-message']
    assert sorted(diags,key=digest)==sorted(products['diagnostics'],key=digest)


def row_roster(jobs):
    assert all(j['kind'] in ('full','link-only','wild') and j['exit']==0 for j in jobs)
    return collections.Counter((j['kind'],j['target']) for j in jobs)


def native_cut(first, repeat, products, arm):
    """Remove only B's duplicate first e2e job, leaving strict target counts to compare."""
    roster=row_roster(first)
    subsequent=row_roster(repeat)
    assert roster['full','ron']==subsequent['full','ron']==1
    source='crates/ty_server/tests/e2e/main.rs'
    group=[j for j in first if j['kind']=='full' and j['target']=='e2e'
           and '--test' in j['argv'] and any(a==source or a.endswith('/'+source) for a in j['argv'])]
    target,=products['e2e']
    links=[j for j in first if j['kind']=='wild' and j['target']==target]
    want=2 if arm=='B' else 1
    assert len(links)==len(group)==want
    assert len({tuple(j['argv']) for j in group})==1
    own=products['ty_server']['file']
    assert all('ty_server='+own in j['argv'] for j in group) and products['ty_server']['fresh']
    if arm=='B':
        roster['full','e2e']-=1
        roster['wild',target]-=1
    return roster,subsequent


def check_raw(actual, allowed):
    assert len(actual)==len(allowed)==110 and set(actual)==set(allowed)
    differences={n:h for n,h in actual.items() if h not in allowed[n]}
    if differences:
        raise ValueError('Unadmitted raw ELF hashes: '+json.dumps(differences,sort_keys=True))


def verified_variants(n, observed, other):
    path=BASE/'wall-native-proofs/variants.json'
    reported=read(path) if path.exists() else {}
    assert set(reported)<=set(observed)
    assert all(name in reported for name,hs in observed.items() if len(hs)>1)
    output={}
    for name, spec in reported.items():
        records=spec['replays']
        assert 2<=len(records)<=12
        values=set(); widths=set(); closed=set(); interpretations=set()
        for row in records:
            paths=[]
            for key in ('receipt','elf'):
                f=(path.parent/row[key]).resolve()
                assert f.is_relative_to(path.parent.resolve()) and f.is_file()
                paths.append(f)
            desc,elf=paths
            assert sha(desc)==row['receipt_sha256']
            e=read(desc);h=sha(elf)
            assert e['exit']==0 and e['target']==name and e['elf_sha256']==h
            assert e['wild_sha256']==P['sdk']['tools']['wild']
            assert e['same_verified_inputs'] and e['threads']>=1
            for key in ('resolved_input_bytes_sha256','argv_except_width_and_output_sha256'):
                assert re.fullmatch('[0-9a-f]{64}',e[key])
            values.add(h);widths.add(e['threads'])
            closed.add((e['resolved_input_bytes_sha256'],e['argv_except_width_and_output_sha256']))
            fields=fingerprint(elf)
            interpretations.add((fields['normalized'],fields['bytes']))
        assert len(values)>=2 and len(widths)>=2 and len(closed)==len(interpretations)==1
        assert observed[name]<=values and observed[name]&values
        output[name]=sorted(values)
    allowed={n:output.get(n,sorted(hs)) for n,hs in observed.items()}
    for v in other:
        check_raw(v,allowed)
    return allowed,sha(path) if reported else None


def evidence(n):
    n.source()
    assert n.w==BASE/'ruff-evaluation-v2' and n.k==BASE/'protocol-v3'
    obs=n.read(n.p/'sdk.json')
    assert obs['archive']==P['sdk']['archive'] and obs['tools']==P['sdk']['tools']
    wild=n.sdk/'lib/rustlib/x86_64-unknown-linux-gnu/bin/wild-ld/ld.bfd'
    driver,=list((n.sdk/'lib').glob('librustc_driver-*.so'))
    for name,f in [('cargo',n.sdk/'bin/cargo'),('rustc',n.sdk/'bin/rustc'),('wild',wild),('driver',driver)]:
        assert sha(f)==obs['tools'][name]
    files={};meta={};physical={};models=[];summaries=[];listings=[];proj={};repeat_projection={};saved_files={}
    for phase in ('seed','observer','composed'):
        assert (n.k/(phase+'.exit')).read_text()=='0'
        files['finish-'+phase]=sha(n.w/(phase+'-complete.json'))
    inventory=read(HERE/'adopted-seed-v2.json')
    assert sha(HERE/'adopted-seed-v2.json')==sha(n.k/'adopted-seed.json')==P['adopted_seed_v2']['raw_inventory_sha256']
    assert read(n.k/'adopted.json')=={'v2':P['adopted_seed_v2']['commit'],'seed':inventory['seed_complete'],'canonical':str(n.can)}
    assert read(BASE/'protocol-v2/registered.json')=={'ref':P['adopted_seed_v2']['commit'],'manifest':P['adopted_seed_v2']['manifest']}
    seed_work=BASE/'ruff-evaluation-v2'
    assert sha(seed_work/'seed-complete.json')==inventory['seed_complete']
    assert (BASE/'protocol-v2/seed.exit').read_text()=='0' and manifest(BASE/'protocol-v2')==inventory['v2_protocol']
    for seed in ('seed-cold','seed-repeat1','seed-repeat2'):
        d=seed_work/seed
        for name in ('command.json','products.json','stdout','stderr'):
            files[seed+'/'+name]=sha(d/name)
        if seed!='seed-cold':
            files[seed+'/physical.json']=sha(d/'physical.json')
            assert n.trace_jobs(d/'trace')==read(d/'physical.json')
        product=read(d/'products.json');record=inventory['commands'][seed]
        assert not product['e2e'] and not read(d/'command.json')['edited']
        assert sha(d/'products.json')==record['product_receipt'] and sha(d/'stdout')==record['stdout']
        assert product['roster']==record['roster'] and product['units']==record['units']==617
        if seed!='seed-cold':
            assert product['counts']=={'full':1,'link-only':48,'wild':48} and product['fresh']==563
        owned={p for row in (json.loads(line) for line in (d/'stdout').read_bytes().splitlines())
               if row['reason']=='compiler-artifact' and row['package_id'].startswith('path+')
               for p in [*row['filenames'],row['executable']] if p}
        workspace={p:h for p,h in product['native'].items() if p in owned}
        registry={p:h for p,h in product['native'].items() if p not in owned}
        assert (len(workspace),len(registry),len(product['exes']))==(108,78,100)
        assert digest(workspace)==record['workspace_sha'] and digest(registry)==record['registry_sha']
    critical=read(seed_work/'seed-complete.json')['ty_server']
    assert critical['fresh'] and sha(n.actual(critical['file'],n.seed))==critical['sha']
    for letter,arm in ROLES.items():
        _,binary=n.sealed_file(arm)
        assert len(binary)==64
        assert binary==P['subject_images'][letter]
        if letter=='B':assert binary==P['control']
        meta[letter]=binary
        for phase in ('selected','repeat'):
            name=phase+'-'+arm;d=n.w/name
            for f in ('command.json','products.json','physical.json','stdout','stderr','e2e-list'):
                files[name+'/'+f]=sha(d/f)
            command=read(d/'command.json');r=read(d/'products.json')
            assert command==dict(arm=arm,binary=binary,code=0,edited=True,traced=True,
                                 command=P['command']+['--message-format=json'])
            assert r['ty_server']==critical
            assert (r['units'],len(r['native']),len(r['exes']),len(r['e2e']))==(619,110,102,1)
            assert set(r['exes'])<=set(r['native']) and not n.actual(r['e2e'][0],n.seed).exists()
            registries=read(d/'registry-native.json')
            assert len(registries)==78 and digest(registries)==P['registry_sha256']
            files[name+'/registry-native.json']=sha(d/'registry-native.json')
            if phase=='selected':
                for snapshot, folder, expected in [('preserved-native.json','native-files',r['native']),
                                                   ('preserved-registry.json','registry-files',registries)]:
                    saved=read(d/snapshot);files[name+'/'+snapshot]=sha(d/snapshot)
                    assert set(saved)==set(expected) and len({v['file'] for v in saved.values()})==len(expected)
                    for target,v in saved.items():
                        assert v['file'].isdigit()
                        archive=d/folder/v['file']
                        assert not archive.samefile(n.actual(target,n.w/('state-'+arm)))
                        assert sha(archive)==v['sha256']==expected[target]
                        if folder=='native-files':saved_files.setdefault(target,[]).append((archive,v['sha256']))
            else:
                for target,h in registries.items():
                    assert sha(n.actual(target,n.w/('state-'+arm)))==h
            events=[json.loads(line) for line in (d/'stdout').read_bytes().splitlines()]
            cargo_roster(events,r)
            physical[name]=read(d/'physical.json')
            assert physical[name]==n.trace_jobs(d/'trace')
            assert {k:v for k,v in collections.Counter(j['kind'] for j in physical[name]).items()}==r['counts']
            models.append(r['native']);summaries.append(summary(r));listings.append(files[name+'/e2e-list'])
        first=read(n.w/('selected-'+arm)/'products.json');after=read(n.w/('repeat-'+arm)/'products.json')
        s,t=native_cut(physical['selected-'+arm],physical['repeat-'+arm],first,letter)
        proj[letter]=sorted(s.items());repeat_projection[letter]=sorted(t.items())
        assert sha(n.actual(critical['file'],n.w/('state-'+arm)))==critical['sha']
        for name,h in after['native'].items():
            assert sha(n.actual(name,n.w/('state-'+arm)))==h
    assert proj['B']==proj['C'] and repeat_projection['B']==repeat_projection['C']
    identities=[]
    for role in ROLES.values():
        identities.append({tuple(j['argv']) for j in physical['selected-'+role] if j['kind']=='full' and j['target']=='e2e'
            and any(a=='crates/ty_server/tests/e2e/main.rs' or a.endswith('/crates/ty_server/tests/e2e/main.rs') for a in j['argv'])})
    assert len(identities[0])==1 and identities[0]==identities[1]
    assert len(set(summaries))==len(set(listings))==1
    assert all(set(m)==set(models[0]) for m in models)
    allowed,variant=verified_variants(n,{f:{m[f] for m in models} for f in models[0]},models)
    for name,options in allowed.items():
        if len(options)>1:
            # Check the actual first-selection files as well as the forced linker witness.
            anchors=list(saved_files[name])
            for arm in ROLES.values():
                f=n.actual(name,n.w/('state-'+arm));anchors.append((f,sha(f)))
            matches={fingerprint(f)['normalized'] for f,h in anchors if h in options}
            proof=read(BASE/'wall-native-proofs/variants.json')[name]
            for v in proof['replays']:
                matches.add(fingerprint(BASE/'wall-native-proofs'/v['elf'])['normalized'])
            assert len(matches)==1 and all(h in options for f,h in anchors)
    counts={name:dict(collections.Counter(j['kind'] for j in jobs)) for name,jobs in physical.items()}
    return dict(subjects=meta, source_plan=P['native_manifest'], files=files, stats=counts, roster=summaries[0],
                repeat_roster=digest(repeat_projection['B']), listing_sha256=listings[0],
                allowed=allowed, registry=registries, registry_sha256=P['registry_sha256'],
                variants_sha256=variant, typed_seed_rlib=critical)


def tree(root):
    """Hash file bytes and relative names, metadata and within-tree hardlink topology."""
    digestor=hashlib.sha256();links={};size=0;count=0
    for f in sorted(root.rglob('*')):
        st=f.lstat();name=str(f.relative_to(root));key=(st.st_dev,st.st_ino)
        if stat.S_ISREG(st.st_mode):
            first=links.get(key)
            if first is None:
                extra=sha(f);links[key]=name;size+=st.st_size
            else:extra=['link',first]
        elif stat.S_ISLNK(st.st_mode):extra=['symlink',os.readlink(f)]
        elif stat.S_ISDIR(st.st_mode):extra=None
        else:raise ValueError('Unsupported seed object: '+name)
        attrs=[(k,hashlib.sha256(os.getxattr(f,k,follow_symlinks=False)).hexdigest())
               for k in sorted(os.listxattr(f,follow_symlinks=False))]
        record=[name, st.st_mode, st.st_uid, st.st_gid, st.st_mtime_ns, extra,attrs]
        digestor.update(json.dumps(record,ensure_ascii=True,separators=(',',':')).encode()+b'\n');count+=1
    return {'digest':digestor.hexdigest(),'objects':count,'unique_file_bytes':size}
