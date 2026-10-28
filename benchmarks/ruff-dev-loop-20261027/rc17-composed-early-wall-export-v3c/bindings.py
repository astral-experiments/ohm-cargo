"""Resolve independent immutable files on the reviewer's disk. This module never fetches them."""
from pathlib import Path
import collections, gzip, hashlib, json, re, sys
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
import stock
from sideproof import check_h2,check_native,NATIVE_READER
from export import WALL, WALL_GIT, BOOT, WALL_B, NATIVE, NATIVE_GIT, STOCK_GIT, STOCK_SRC, CONT_GIT, CONT_SRC, WALL_PARENT, STOPPED_GIT, canonical, dig, file_sha

def read(p):return json.loads(p.read_bytes())

def manifest(path,want):
    assert re.fullmatch('[0-9a-f]{64}',want) and file_sha(path/'SHA256SUMS')==want
    names=set()
    for row in (path/'SHA256SUMS').read_text().splitlines():
        h,n=row.split('  ',1);rel=Path(n);assert n not in names and not rel.is_absolute() and '..' not in rel.parts
        f=path/rel;assert f.is_file() and not f.is_symlink() and f.resolve().is_relative_to(path.resolve()) and file_sha(f)==h
        names.add(n)
    return names

def verified_file(root,names,name,want):
    assert name in names and file_sha(root/name)==want;return root/name

def ext_bundle(descriptor,root):
    assert set(descriptor)=={'ref','manifest','files'} and re.fullmatch('[0-9a-f]{40}',descriptor['ref'])
    names=manifest(root,descriptor['manifest'])
    result={}
    for label,entry in descriptor['files'].items():
        assert set(entry)=={'path','sha256'}
        result[label]=verified_file(root,names,entry['path'],entry['sha256'])
    return result

def bind_external(pin,catalog,admission,h2=None):
    assert set(pin)=={'catalog','admission','h2'}
    cc=pin['catalog'];cf=ext_bundle(cc,catalog)
    required_files={'view_gzip':'wall-view.json.gz','terminal':'terminal.json','registration':'registration.json','continuation':'continuation-registration.json','before':'tree-before-resume.json','after':'physical-preservation.json','bootreg':'bootstrap-registration.json','completion':'bootstrap-completion.json'}
    assert set(cf)==set(required_files)|{'independent'} and all(cf[k]==catalog/n for k,n in required_files.items())
    assert cc['ref'] not in (WALL_GIT,WALL_PARENT,WALL_B,BOOT,STOCK_GIT,CONT_GIT,STOPPED_GIT,NATIVE_GIT)
    # All public per-target native receipts, including the two rejected-slot reconstructions.
    assert not (catalog/'links').is_symlink()
    members=manifest(catalog,cc['manifest'])
    assert {str(f.relative_to(catalog)) for f in (catalog/'links').glob('*.json.gz')}<={*members}
    required={'commands.json.gz','wall-view.sha256','reconstructions/failure-1.json','reconstructions/failure-2.json'}
    assert required<=members
    score=stock.verify(catalog,cf['independent']);assert score['native_occurrences']==299 and score['stock_wild_processes']==9867 and score['clocks']==0
    view_raw=gzip.decompress(cf['view_gzip'].read_bytes());view=json.loads(view_raw);ind=read(cf['independent'])
    reg=read(cf['registration']);assert reg['commit']==STOCK_GIT and reg['protocol']==STOCK_SRC
    assert read(cf['terminal']).keys()==view['targets'].keys() and ind['accepted'] is True and ind['admitted_or_failed_states_modified']==0
    hashes={'view_sha256':dig(view_raw),'terminal_sha256':file_sha(cf['terminal']),'verifier_receipt_sha256':file_sha(cf['independent'])}
    bundle={'wall_ref':WALL_GIT,'catalog_ref':cc['ref'],'catalog_manifest':cc['manifest'],'catalog_hashes':hashes,'stock_checks':score,'view':view,'independent':ind,
            'continuation':{k:file_sha(cf[k]) for k in ('continuation','before','after','bootreg','completion')}}
    if pin['h2'] is not None:
        assert h2 is not None and pin['h2']['ref'] not in (WALL_GIT,WALL_PARENT,WALL_B,BOOT,STOCK_GIT,CONT_GIT,STOPPED_GIT,NATIVE_GIT,cc['ref'])
        # The separate H2 lane only contributes its independently pinned terminal marker.
        # Reading its 48 slot results adds no authority to an H5 release.
        hp=pin['h2'];assert set(hp)=={'ref','manifest','files'} and re.fullmatch('[0-9a-f]{40}',hp['ref']) and set(hp['files'])=={'terminal','host'}
        mf=h2/'SHA256SUMS';assert not mf.is_symlink() and file_sha(mf)==hp['manifest']
        entry=hp['files']['terminal'];assert set(entry)=={'path','sha256'}
        name=entry['path'];rel=Path(name);assert not rel.is_absolute() and '..' not in rel.parts
        matched=[row for row in mf.read_text().splitlines() if row.split('  ',1)[1]==name]
        assert matched==[entry['sha256']+'  '+name]
        ht=h2/rel;assert ht.is_file() and ht.resolve()==h2.resolve()/rel and file_sha(ht)==entry['sha256']
        end=ht.read_bytes();assert end
        hr=hp['files']['host'];assert set(hr)=={'path','sha256'} and hr['path']=='host-receipts.json'
        hf=h2/hr['path'];assert hf.is_file() and hf.resolve()==h2.resolve()/hr['path'] and file_sha(hf)==hr['sha256']
        assert [l for l in mf.read_text().splitlines() if l.split('  ',1)[1]==hr['path']]==[hr['sha256']+'  '+hr['path']]
        physical=read(hf);check_h2(physical,entry['path'],entry['sha256'])
        if ht.name=='failure.txt':mode='failed'
        else:
            row=json.loads(end);assert row['phase']=='all_slots_finished' and row['slots']==48;mode='complete'
        bundle['h2']={'ref':pin['h2']['ref'],'file':pin['h2']['files']['terminal']['path'],'sha256':dig(end),'status':mode,'physical':physical}
    else:assert h2 is None
    if pin['admission'] is None:
        assert admission is None;return bundle
    ac=pin['admission'];assert ac['ref'] not in (WALL_GIT,WALL_PARENT,WALL_B,BOOT,STOCK_GIT,CONT_GIT,STOPPED_GIT,NATIVE_GIT,cc['ref']);af=ext_bundle(ac,admission)
    assert set(af)=={'native','ci','catalog_publication','witness','proof','bootreg','completion','provenance'}
    assert file_sha(af['bootreg'])==bundle['continuation']['bootreg'] and file_sha(af['completion'])==bundle['continuation']['completion'] and file_sha(af['proof'])==hashes['verifier_receipt_sha256']
    witness=read(af['witness']);assert witness['independent_review']=='accepted' and (witness['workspace_linked_targets'],witness['fresh_occurrences'],witness['registry_exact'],witness['historical_native_ref'])==(50,297,78,NATIVE_GIT) and all(witness[k]==v for k,v in hashes.items())
    check_native(witness,view,hashes)
    assert verified_file(catalog,members,'root-native-reread.py',NATIVE_READER)
    prov=read(af['provenance']);assert prov['reread_source_sha256']==NATIVE_READER and prov['catalog_result_ref']==cc['ref'] and prov['bootstrap_ref']==BOOT
    assert verified_file(catalog,members,prov['root_witness_file'],file_sha(af['witness'])) and cf['independent']==catalog/prov['independent_verifier_file']
    bundle['published_proofs']={k:file_sha(af[k]) for k in ('witness','proof','bootreg','completion','provenance')}
    bundle.update(admission_ref=ac['ref'],admission_manifest=ac['manifest'],admission_sha=file_sha(af['native']),
                  ci_sha=file_sha(af['ci']),catalog_publication_sha=file_sha(af['catalog_publication']))
    return bundle

def original_native(path):
    manifest(path,NATIVE)
    return [json.loads(gzip.decompress((path/name).read_bytes())) for name in ('native.json.gz','replay.json.gz')]+[read(path/'h5-frozen-native-guard.json')]

def model(plan,protocol,controls,old,n,public,catalog_binding):
    import catalog
    from native_registration import SOURCE_REF,SOURCE_MANIFEST
    assert {k:v for k,v in controls.items() if k not in ('allowed','native_catalog')}=={k:v for k,v in old.items() if k!='allowed'}
    canon=Path(n['canonical']);prior={str(Path(k).relative_to(canon)):set(v) for k,v in old['allowed'].items()}
    view=public['view'];hist=json.loads(gzip.decompress((protocol/'historical-links.json.gz').read_bytes()))
    assert hist['native_reference']==view['native_ref']==NATIVE_GIT and hist['native_manifest']==NATIVE and hist['canonical']==str(canon)
    assert set(hist['phases'])==set(view['historical'])==set(view['fresh'])==set(catalog.PHASES)
    def identities(rows):return sorted((r['target'],r['exec_sha256'],r['argv_sha256']) for r in rows)
    assert all(identities(hist['phases'][ph])==identities(view['historical'][ph]) for ph in catalog.PHASES)
    assert set(view['targets'])<=set(prior) and len(prior)==110 and len(view['targets'])==50
    adopt={k:sorted(v) for k,v in prior.items()};byphase=collections.defaultdict(set);all_recipes=set()
    for ph,rows in view['fresh'].items():
        expected=collections.Counter(j['target'] for j in hist['phases'][ph])
        assert collections.Counter(j['target'] for j in rows)==expected
        for j in rows:
            t=j['target'];key=j['recipe'];assert key not in all_recipes and re.fullmatch('[a-f0-9]{64}',key);all_recipes.add(key)
            assert j['kind']==catalog.expected_kind(ph,t) and j['exit']==0
            rule=view['targets'][t]['recipes'][key]
            assert rule['phase']==ph and rule['occurrence']==j['occurrence'] and rule['stable_argv_sha256']==j['argv_sha256']
            assert stock.digest(sorted(rule['bodies']))==stock.digest(sorted({v['plain_sha256'] for v in rule['widths']}))
            assert j['raw_sha256'] in rule['bodies'];byphase[ph,t].update(rule['bodies'])
        for t in expected:assert n['steps'][ph]['workspace'][t] in byphase[ph,t]
    assert len(all_recipes)==297
    for t,value in view['targets'].items():
        members=set(value['recipes']);assert members=={j['recipe'] for ph in catalog.PHASES for j in view['fresh'][ph] if j['target']==t}
        union=set().union(*(byphase[ph,t] for ph in catalog.PHASES));assert prior[t]<=union;adopt[t]=sorted(union)
    assert sum(k not in view['targets'] and len(v)==1 for k,v in adopt.items())==60
    stopped=plan['stopped_v2'];bad={k:stopped['unadmitted'][Path(k).name] for k in prior if Path(k).name in stopped['unadmitted']}
    assert len(bad)==2 and all(v in byphase['repeat-observer',k] and v not in prior[k] for k,v in bad.items())
    assert controls['allowed']=={str(canon/k):v for k,v in adopt.items()}
    pub=catalog_binding;cat=controls['native_catalog'];s=public['stock_checks'];ind=public['independent']
    assert sum(len(x) for x in view['fresh'].values())==sum(map(len,hist['phases'].values()))==297
    assert ind['phase_occurrences']=={ph:len(v) for ph,v in view['fresh'].items()}
    assert (ind['all_untimed_stock_wild_processes'],ind['explicit_reported_and_plain'],ind['ordinary_stock_controls'])==(9867,9568,299)
    assert cat==dict(plan_ref=WALL_GIT,catalog_protocol_ref=BOOT,catalog_result_ref=public['catalog_ref'],
        registered_catalog_sha256=public['catalog_publication_sha'],catalog_view_sha256=pub['view_sha256'],
        terminal_sha256=pub['terminal_sha256'],independent_verification_sha256=pub['verifier_receipt_sha256'],ci_sha256=public['ci_sha'],
        widths=list(range(1,17)),linked_targets=50,exact_others=60,historical_occurrences=297,fresh_occurrences=297,input_families=297,
        raw_sha256_sets=dig(canonical(adopt)),prior_failure_sha256=stopped['first_failure_sha256'],native_protocol_ref=SOURCE_REF,
        native_protocol_manifest=SOURCE_MANIFEST,independent_plain_and_reporting=9568,independent_ordinary_links=299,literal_recipes=297,**public['lineage_model'])
    return controls
