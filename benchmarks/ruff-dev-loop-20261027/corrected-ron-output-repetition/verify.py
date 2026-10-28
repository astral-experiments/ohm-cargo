"""Verify ten real Cargo phase rosters, the isolated release-compiler replays and every ELF field."""
import collections,gzip,hashlib,json
from pathlib import Path
D=Path(__file__).resolve().parent
def load(name):return json.loads(gzip.decompress((D/name).read_bytes()))
A=load('original.json.gz');B=load('supplement.json.gz')
assert A['command']==['cargo','+ohm','test','--no-run','--workspace','--locked','--offline','-j8','--message-format=json']
assert A['zero_clocks'] and A['default_trust'] and A['cargo']=='0aa04df8023984b83ef676d1494d43e482472e1b2bccdb82a4d0bd390578a322' and A['rustc']=='52d5c046f570d3d61ff8bbaeff0d44798df916306110b4a2cac7fe459bc11955'
allrows={**A['primary'],**B['extra_commands']};order=['cold',*['unchanged-'+str(i)for i in range(1,4)],*['extra-'+str(i)for i in range(1,7)]]
assert set(allrows)==set(order);cold=allrows['cold'];old=None;equal=[];native_differences={}
for label in order:
    r=allrows[label]
    assert r['units']==619 and r['program_files']==len(r['native_outputs'])==110 and r['profile_executable']=={'test':84,'normal':18}
    if label!='extra-1':assert r['reader']==cold['reader'] and r['cargo_roster']==cold['cargo_roster'] and r['diagnostics']==cold['diagnostics']
    assert cold['reader']['listings']['stdlib'][0]==4 and cold['reader']['listings']['ty_server'][0]==200 and 'E712' in cold['reader']['lint']
    assert r['archive']==cold['archive'] and r['ar_members']==cold['ar_members'] and len(r['ar_members'])==12 and r['foreign_marker']
    assert r['root']==cold['root'] and r['cargo_public_api']==cold['cargo_public_api'] and r['depfile']==cold['depfile'] and r['fingerprint']==cold['fingerprint']
    ron,=r['actual_ron'];assert not ron['binary_depdepinfo'] and not ron['explicit_checksum'] and ron['args']==cold['actual_ron'][0]['args'] and len(ron['ordered_rust_input_positions'])==6
    rustcs=collections.Counter(j[2]for j in r['rustc_jobs']);wild=list(r['wild_jobs'].values());assert rustcs==r['mode_counts']['rustc'] and len(wild)==r['mode_counts']['wild']
    assert not any(j['standalone_rmeta']for j in wild) and not any(j['literal_response_files']for j in wild)
    if label=='cold':
        assert r['fresh']==0 and rustcs=={'full':636} and len(wild)==201
    else:
        assert r['fresh']==563 and rustcs=={'full':1,'link-only':50} and len(wild)==len({j['destination']for j in wild})==50
        assert {j[1]for j in r['rustc_jobs']if j[2]=='full'}=={'ron'}
        assert collections.Counter(len(j['ron_archive'])for j in wild)=={1:35,0:15}
        assert {j['destination']for j in wild}=={j['destination']for j in allrows['unchanged-1']['wild_jobs'].values()}
        assert r['previous_full_metadata_byte_delta']['old_sha256']==old['metadata'] and r['previous_full_metadata_byte_delta']['new_sha256']==r['metadata']
        if old['metadata']==r['metadata']:equal.append(label)
    native_differences[label]=[Path(p).name for p,v in r['native_outputs'].items()if cold['native_outputs'][p]!=v]
    old=r
assert equal==['unchanged-3','extra-6'] and len({v['metadata']for v in allrows.values()})==4
assert [allrows[k]['previous_full_metadata_byte_delta']['changed_bytes_in_common_length']for k in order[1:4]]==[139,56,0]
known={'document-1dd8f0784781d62c','ty_python_semantic-a879b0690f634244'}
assert {n for k in order[:4]for n in native_differences[k]}==known
all_six=known|{'ruff_db-0ac3a038ac77fe63','fixtures-b5bc133c5943322a','simple_tokenizer-c639259863b397fa','e2e-8fa23882290527ed'}
assert set(n for g in native_differences.values()for n in g)==all_six
gen=B['output_generations'];m=[];ar=[]
for label in ['initial',*order[4:]]:
    f=gen[label]['ron_generation'];lib,=[v for n,v in f.items() if n.endswith('.rlib')];met,=[v for n,v in f.items()if n.endswith('.rmeta')];row=allrows['unchanged-3' if label=='initial'else label]
    assert lib['sha256']==row['archive'] and met['sha256']==row['metadata'];ar.append(lib['mtime_ns']);m.append(met['mtime_ns'])
assert len(set(m))==1 and all(x<y for x,y in zip(ar,ar[1:]))
try1=B['original_supplement_reporter'];assert try1['outer_rc']==1 and try1['command']=={'rc':0,'elapsed_ns':None} and allrows['extra-1']['reader']is None
widths={**B['width_replay'],**load('width-extra.json.gz')}
for name,count in [('document',277),('ty_python_semantic',479),('ruff_db',358),('fixtures',249),('simple_tokenizer',136),('e2e',397)]:
    w=widths[name];x=w['native'];ww=x['widths'];assert len(x['simultaneous_operands'])==count and x['same_resolved_positive_operand_bytes_after_all_links'] and x['native_binary']=='0d6335808b647d499f3d74993b602e64ff0625206c809bf4913c487eea380cd5'
    assert len(set(ww.values()))==2 and len({ww[k]for k in ['2','4','8','16','default']})==1 and ww['1']!=ww['2'] and w['historical_raw_sha256_parity']
    assert set(w['workspace_outputs'].values())==set(ww.values()) and all(w['reproduced'].values())
    a,b=w['decoded'][ww['1']],w['decoded'][ww['2']];assert a['size']==b['size'] and a['exact_fields']==b['exact_fields'] and a['every_other_byte_sha256']==b['every_other_byte_sha256']
    assert sorted((s,l)for _,s,l in a['exact_fields'])==[(8,'sh_entsize'),(32,'build-id')]
    assert a['gnu_build_id']!=b['gnu_build_id'] and {a['rodata_sh_entsize'],b['rodata_sh_entsize']}==({0,1}if name=='fixtures'else{0,8})
    assert {k for k in a['sections']if a['sections'][k]!=b['sections'][k]}=={'.rodata','.note.gnu.build-id'}
    assert a['sections']['.rodata']['data']==b['sections']['.rodata']['data'] and a['sections']['.rodata']['header'][:-1]==b['sections']['.rodata']['header'][:-1]
    assert a['sections']['.note.gnu.build-id']['header']==b['sections']['.note.gnu.build-id']['header'] and a['sections']['.note.gnu.build-id']['data']!=b['sections']['.note.gnu.build-id']['data']
rr=A['captured_compiler_replay'];assert rr['summary']['donor_untouched'] and not rr['summary']['same_ordinary_products'] and rr['summary']['same_explicit_products']
pr=rr['products'];names=pr['normal1'];lib,=[q for q in names if q.endswith('.rlib')];md,=[q for q in names if q.endswith('.rmeta')]
assert len({pr[k][lib]['sha256']for k in ['normal1','normal2','normal3','donor']})==1 and len({pr[k][md]['sha256']for k in ['normal1','normal2','normal3','donor']})==3 and rr['normal1_to_2']['changed_bytes_in_common_length']==56
assert pr['explicit1']==pr['explicit2'] and len(rr['inputs']['externs'])==6
actual=load('operands.json.gz')['by_phase'];derived={}
for key,rows in actual.items():
    assert len(rows)==50 and set(rows)==set(allrows[key]['wild_jobs'])
    layouts=collections.Counter();dyn=collections.Counter();missing=[]
    for n,rec in rows.items():
        assert rec['raw_argv_sha256']==allrows[key]['wild_jobs'][n]['argv'] and rec['raw_trace_line_sha256']==allrows[key]['wild_jobs'][n]['raw_execve_sha256']
        layout=tuple(z['role'].split('/')[2]for z in rec['search_directories_in_order']if z['role'].startswith('target/unit/'));layouts[layout]+=1
        assert rec['libraries_in_order']==[{'mode':'dynamic','name':k}for k in ['gcc_s','util','rt','pthread','m','dl','c']]
        assert rec['explicit_scripts']==rec['response_files']==[] and len(rec['operand_native_files'])==5 and all(z['root']=='system'and z['kind']=='elf'for z in rec['operand_native_files'])
        assert [z[0]for z in rec['compiler_and_plugin_options']]==['-plugin','plugin-option-path','plugin-resolution','-dynamic-linker']
        assert len(rec['search_directories_in_order'])==11+len(layout)
        if not rec['bundle_rlibs']:missing.append([rec['target']['package'],rec['target']['name'],rec['target']['kind']])
    assert layouts=={('psm',):16,('psm','zstd-sys'):21,('psm','zstd-sys','tikv-jemalloc-sys'):13} and len(missing)==15
    derived[key]=sorted(missing)
assert all(v==derived['unchanged-1']for v in derived.values())
print(json.dumps({'whole_cargo_commands':len(order),'uncatalogued_reader':1,'fresh_after_cold':563,'warm_full_rustcs':9,'warm_link_only_rustcs':450,'warm_wild':450,'byte_equal_producer_transitions':equal,'distinct_standalone_rmeta':4,'bare_linked_ron_archive_by_warm_command':35,'warm_outputs_without_ron':15,'same_native_input_release_width_replays':36,'real_timing_samples':0},sort_keys=True))
