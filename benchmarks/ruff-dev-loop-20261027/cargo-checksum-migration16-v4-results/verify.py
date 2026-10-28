"""Reopen six job rosters, all path hashes and reader data independently of the measurement process."""
import collections,gzip,hashlib,json,re
from pathlib import Path
p=Path(__file__).resolve().parent
def h(b):return hashlib.sha256(b).hexdigest()
def load(n):
    raw=(p/n).read_bytes()
    return json.loads(gzip.decompress(raw) if n.endswith('.gz') else raw)
plan=load('plan.json');old_binding=load('prior-binding.json');originals=load('originals.json')
hdr=load('changed-headers.json');elves=load('changed-elf.json')
ranges={'check':(520,71,449,0,6,6),'build':(501,68,433,0,15,15),'test':(619,162,456,1,110,110)}
def profile(z):return sorted(json.dumps({k:v for k,v in row.items() if k!='fresh'},sort_keys=True)for row in z['unit-roster'])
def echo(x):return {k:{l:v[l]for l in ['exit','stdout_sha','stderr_sha','primary','secondary','names','error_message'] if l in v} for k,v in x.items()}
report={}
for mode,(n,native,mtime,obs,links,workspace_elf)in ranges.items():
    base=load(mode+'-stock-control.json.gz');initial=load(mode+'-initial-wire.json.gz');copies=load(mode+'-input-copy.json')
    assert h((p/(mode+'-stock-control.json.gz')).read_bytes())==old_binding[mode+'-stock-control.json.gz']['sha256']
    by=copies['released_seed'];assert by['sha256']==copies['new_isolated_input']['sha256']==plan['seed_trees'][mode]
    assert copies['independent_regular_inodes'] and by['files']==copies['unique_regular_inodes']
    assert copies['class_counts']==initial['counts']=={'legacy-ordinary-checksum-retrain':native,'ordinary-mtime':mtime,**({'obs1-safe-complete':obs}if obs else {})}
    refs=base['products'];wire=initial['rows'];assert len(wire)==n and set(wire)==set(base['wire-records']['rows'])
    assert all(v['version']==2 and v['space_names']==v['lossy_or_replacement_names']==0 and v['sha256']==base['wire-records']['rows'][k]['sha256'] for k,v in wire.items())
    assert base['receipt']['fresh']==base['receipt']['units']==n and not base['receipt']['physical'] and base['receipt']['cargo_image']==plan['official_cargo_sha256']
    ris={k for k,v in wire.items()if v['class']=='legacy-ordinary-checksum-retrain'};ids={Path(k).parent.parent.name for k in ris};assert len(ids)==native
    cells=[load(mode+'-'+tag+'.json.gz') for tag in ['first','second']]
    for i,(u,tag) in enumerate(zip(cells,['first','second'])):
        receipt=u['receipt'];calls=u['all-physical-typed-processes']
        assert receipt['command']==plan['commands'][['check','build','test'].index(mode)]
        assert receipt['exit']==0 and receipt['units']==n and receipt['source']==plan['source'] and receipt['cargo_image']==plan['new_cargo_sha256']
        assert all(receipt[k]==base['receipt'][k] for k in ('compiler','driver','linker','lock'))
        assert all(float(v)>25*2**30 for v in receipt['floor'].values())
        for f,dig in u['protocol-original-shas'].items():assert dig==originals[mode+'/final-v4/'+tag+'/'+f]
        assert len(u['unit-roster'])==n and profile(u)==profile(base)
        assert len(calls)==len(set(c['pid'] for c in calls))
        assert dict(collections.Counter(c['role']for c in calls))==receipt['physical']
        assert all(c['exit']==0 for c in calls)
        assert receipt['fresh']==sum(bool(v['fresh'])for v in u['unit-roster'])==(n if i else n-native)
        assert receipt['physical']==({} if i else {'rustc-full':native,'cc':links,'collect2':links,'wild':links,'build-script':5})
        joins=u['compiler-record-joins'];assert joins['entry_count']==len(joins['units'])==n
        jobs=joins['physical'];assert len(jobs)==(0 if i else native)
        assert set(j['id']for j in jobs)==(set()if i else ids)
        actual={c['pid']:c for c in calls};assert all(j['id_basis']=='actual-out-dir' and j['workspace_source'] and j['before_class']=='legacy-ordinary-checksum-retrain' and j['after_class']=='current-ordinary-checksum' and j['argv_sha256']==actual[j['pid']]['arg_sha256'] for j in jobs)
        after=u['wire-records']['rows'];assert after.keys()==wire.keys();assert ris=={k for k,v in after.items()if v['sha256']!=wire[k]['sha256']}
        assert all(v['space_names']==v['lossy_or_replacement_names']==0 for v in after.values())
        assert all((v['version']==4 and v['class']=='current-ordinary-checksum')if k in ris else (v==wire[k])for k,v in after.items())
        assert sum(v['elf'] and v['workspace']for v in u['products'].values())==workspace_elf
        diff={k:{'before':refs.get(k),'after':u['products'].get(k)}for k in refs.keys()|u['products'].keys()if refs.get(k)!=u['products'].get(k)}
        assert u['changed-products']==diff and all(q['before']and q['after'] and q['before']['workspace'] and q['after']['workspace'] for q in diff.values())
        assert echo(u['ordinary-readers'])==echo(base['ordinary-readers'])
        assert u['diagnostics']==base['diagnostics'] and u['executable-artifact-profiles']==base['executable-artifact-profiles']
    assert cells[0]['products']==cells[1]['products'] and cells[0]['wire-records']==cells[1]['wire-records']
    changed=cells[0]['changed-products'];classes=collections.Counter('ELF' if v['before']['elf']else Path(k).suffix for k,v in changed.items())
    hs=hdr[mode]['pairs'];assert {'@cache/'+k for k in hs}=={k for k in changed if k.endswith('.rmeta')}
    verify_headers=collections.Counter()
    for k,obj in hs.items():
        v=changed['@cache/'+k];a,b=obj['original'],obj['retrained']
        assert [a['sha'],b['sha']]==[v['before']['sha256'],v['after']['sha256']] and a['status']==b['status']==0
        zz='same-public-id-different-private' if a['public']==b['public'] and a['stable_id']==b['stable_id'] and a['private']!=b['private']else 'other'
        assert obj['class']==zz;verify_headers[zz]+=1
    assert {'@cache/'+k for k in elves[mode]}=={k for k,v in changed.items()if v['before']['elf']}
    native_results=[]
    for k,z in elves[mode].items():
        v=changed['@cache/'+k];assert z['raw']==[v['before']['sha256'],v['after']['sha256']]
        a,b=z['all_sections']['stock'],z['all_sections']['retrained'];rd={key for key in a if a[key]!=b[key]};assert rd==set(z['section_differences'])
        if z['only_rodata_entsize_and_gnu_build_id']:
            assert z['file_sizes'][0]==z['file_sizes'][1] and z['masked'][0]==z['masked'][1] and z['rodata_entsize'][0]!=z['rodata_entsize'][1]
            assert rd=={'.rodata','.note.gnu.build-id'} and a['.rodata']['bytes']==b['.rodata']['bytes']
        if z['is_test_harness']:
            assert z['list_equal'];ls=[];norm=[]
            for arm in ['stock-repeat','final-v4']:
                def raw(check,stream):
                    s=arm+'-'+check+'.'+stream
                    r=gzip.decompress((p/('native-'+mode+'-'+z['case_id']+'-'+s+'.gz')).read_bytes())
                    assert originals['changed-all-elf-v4/'+mode+'-'+z['case_id']+'/'+s]==h(r);return r
                label=z['list_results'][arm];lines=raw('list','stdout');ls.append(lines)
                assert h(lines)==label['stdout_sha256'] and h(raw('list','stderr'))==label['stderr_sha256'] and label['exit']==0
                assert label['names']==[l.rsplit(': ',1)[0]for l in lines.decode().splitlines()if l.endswith(': test')]
                for j,fil in enumerate(z['filter_results']):
                    irow=fil['arms'][arm];part='filter-'+str(j);s=raw(part,'stdout');e=raw(part,'stderr')
                    assert h(s)==irow['stdout_sha256'] and h(e)==irow['stderr_sha256'] and irow['exit']==0
                assert irow['passed'] and b'1 passed; 0 failed;'in s
                no_clock=re.sub(rb'finished in [0-9.]+s',b'finished in <elapsed>',s)
                assert h(no_clock)==irow['normalized_stdout_sha256'];norm.append(no_clock)
            assert ls[0]==ls[1] and norm[0]==norm[1]
        native_results.append({'artifact':z['artifact'],'section_changes':sorted(rd),'mask_covers_all_other_bytes':z['only_rodata_entsize_and_gnu_build_id'],'changed_bytes':z['raw_ranges']['total_differing_bytes'],'rodata_entsize':z['rodata_entsize'],'identical_listing_size':len(z['list_results']['stock-repeat']['names'])if z['is_test_harness']else None})
    report[mode]={'total_units':n,'first_fresh':cells[0]['receipt']['fresh'],'first_jobs':cells[0]['receipt']['physical'],'all_second_fresh_and_no_jobs':True,'retained_record_classes':initial['counts'],'final_record_classes':cells[0]['wire-records']['counts'],'raw_output_differences':classes,'changed_header_facts':verify_headers,'changed_executables':native_results,'all_ordinary_readers_preserved':True,'v3_v4_product_difference_count':len(load('v3-to-v4-products.json')[mode]['raw_mismatch'])}
print(json.dumps(report,sort_keys=True,indent=2))
