"""Verify the portable complete source/phase/allocation projection without a private devbox."""
import gzip,hashlib,json,re,statistics,sys
from pathlib import Path

def check(p):
    digest=lambda b:hashlib.sha256(b).hexdigest()
    assert p['schema']==1 and p['registration']=='064658706dbe2975ba7080449442163f55b3c6a9af699b850cd001bc8c2cc2c0'
    assert p['physical_kit']['members']==57 and p['physical_kit']['driver']=='9de25028ec1b4ed84c8e5398aecc6e1672236bfdea69ace42dd856d9ada1feff'
    assert p['physical_kit']['cargo']=='1d06626bcef3c5235676ada14f4b7107f56e98aef620f81b0e0c47381dbe0add'
    assert p['physical_kit']['wild']=='0d6335808b647d499f3d74993b602e64ff0625206c809bf4913c487eea380cd5'
    phs=['empty-A','first-B','return-A','return-B','unchanged-B'];slots={'off-storage':phs,'on-storage':phs,'off-clean-B':['empty-B'],'on-clean-B':['empty-B']};assert set(p['slots'])==set(slots)
    roles0=None
    for case,phases in slots.items():
        shown=p['physical_kit']['installations'][case];fs=p['filesystems'][case]
        assert re.fullmatch('[0-9a-f]{64}',shown['source_receipt']) and len(shown['roles'])==57
        if roles0 is None:roles0=shown['roles']
        assert roles0==shown['roles'] and all(len(v)==6 and all(isinstance(x,int) for x in v[:5]) and re.fullmatch('[0-9a-f]{64}',v[-1]) for v in roles0.values())
        assert roles0['bin/cargo'][-1]==p['physical_kit']['cargo'] and roles0['bin/rustc'][-1]=='fb5c1341de5f7ea9350478b52383cb407d6d184bc257e2941ff998fcdec4df18' and roles0['lib/librustc_driver-4fa76f30fa0fea85.so'][-1]==p['physical_kit']['driver'] and roles0['lib/rustlib/x86_64-unknown-linux-gnu/bin/wild-ld/ld.bfd'][-1]==p['physical_kit']['wild']
        assert fs['working_source']['kind']==fs['target_and_build']['kind']=='tmpfs' and fs['working_source']['size']==6*2**30 and fs['target_and_build']['size']==10*2**30 and fs['target_and_build']['device']!=fs['working_source']['device']

        arm=case.split('-')[0];history=p['slots'][case];assert set(history)==set(phases);prev=0
        for phase in phases:
            r=history[phase]; assert len(r['full_hash'])==64 and r['full_hash']==p['integrated_readback']['slots'][case][phase]['cli']['sha256']
            inc,all_,exclusive,across=r['incremental'],r['all'],r['incremental_exclusive'],r['incremental_other_alias']
            assert inc==exclusive+across and all_==r['target']+r['build']-r['target_build_intersection'] and 0<inc<all_
            assert r['physical']==p['integrated_readback']['slots'][case][phase]['physical']
            assert r['sample_start']==prev and r['sample_end']==all_ and r['peak']>=max(prev,all_)
            assert re.fullmatch('[0-9a-f]{64}',r['native']['tar_sha256']) and re.fullmatch('[0-9a-f]{64}',r['native']['fd_ledger_sha'])
            assert r['rows']==375 and r['jobgraph']=='38d3fd49b035775102dd433f08a9bbc99dfe7b883e1bbf22f10d91b542433adb'
            assert 0<r['gap_ns']['min']<=r['gap_ns']['median']<=r['gap_ns']['p99']<=r['gap_ns']['max']
            assert set(r['verdicts'])=={'version','source','clean','warning','fixed','recheck','invalid'}
            assert [r['verdicts'][k]['status'] for k in ['version','source','clean','warning','fixed','recheck','invalid']]==[0,0,0,1,1,0,1]
            for v in r['verdicts'].values():assert all(re.fullmatch('[0-9a-f]{64}',v[k]) for k in ('stdin_sha256','stdout_sha256','stderr_sha256'))
            assert r['reader_stdout']==('Expr=64 valid=1 rejected' if phase.endswith('-A') else 'Expr=56 valid=1 rejected')
            if phase.startswith('empty'): assert [r['dirty'],r['physical']['SDK rustc'],r['physical']['stock Wild'],r['physical']['build script']]==[375,379,69,37]
            elif phase.startswith('unchanged'):assert r['dirty']==0 and r['physical']=={}
            else:assert r['dirty']==20 and r['physical']=={'GCC':1,'SDK rustc':20,'build script':1,'collect2':1,'stock Wild':1}
            if arm=='off' or phase.startswith('empty'):assert r['tables']['packed']['unique_inodes']==0
            else:assert r['tables']['packed']['unique_inodes']>0
            prev=all_
        if case.endswith('-storage'):
            groups=[[history['empty-A'],history['return-A']],[history[k] for k in ('first-B','return-B','unchanged-B')]+[p['slots'][arm+'-clean-B']['empty-B']]]
            for group in groups:
                assert len({r['full_hash'] for r in group})==len({r['reader_hash'] for r in group})==1
                assert len({json.dumps(r['verdicts'],sort_keys=True) for r in group})==1
    out={}
    for ph in phs:
        a,b=(p['slots'][m+'-storage'][ph] for m in ['off','on']);out[ph]={}
        for k,pubname in [('all','whole'),('incremental','incremental'),('peak','peak')]:
            d=b[k]-a[k]; ratio=b[k]/a[k]
            official=p['integrated_readback']['deltas'][ph][pubname]
            assert [a[k],b[k],d,ratio]==[official[x] for x in ('off','on','delta_bytes','ratio_on_off')]
            out[ph][pubname]=(a[k],b[k],d,ratio)
    return out

def negatives(p):
    import copy
    failures=[]
    def poke(k,fn):
        q=copy.deepcopy(p);fn(q)
        try:check(q)
        except (AssertionError,KeyError):failures.append(k)
        else:raise AssertionError('accepted '+k)
    def row(q):return q['slots']['on-storage']['return-A']
    poke('hardlink counted twice',lambda q:row(q).__setitem__('target_build_intersection',row(q)['target_build_intersection']+4096))
    poke('unobserved peak',lambda q:row(q).__setitem__('peak',row(q)['sample_end']-1))
    poke('clean ELF mismatch',lambda q:q['slots']['on-clean-B']['empty-B'].__setitem__('full_hash','0'*64))
    poke('missing stock Wild',lambda q:row(q)['physical'].__setitem__('stock Wild',0))
    poke('wrong branch semantics',lambda q:row(q).__setitem__('reader_stdout','Expr=56 valid=1 rejected'))
    poke('false positive malformed verdict',lambda q:row(q)['verdicts']['invalid'].__setitem__('status',0))
    poke('missing packed table',lambda q:row(q)['tables']['packed'].__setitem__('unique_inodes',0))
    poke('changed rustc physical inode',lambda q:q['physical_kit']['installations']['on-storage']['roles']['bin/rustc'].__setitem__(1,0))
    poke('source data charged to output volume',lambda q:q['filesystems']['off-storage']['target_and_build'].__setitem__('device',q['filesystems']['off-storage']['working_source']['device']))
    return failures
def verify_diagnostic(p,base):
    c=p['separate_controls']; g=p['separate_diagnostic']
    assert c['registration']=='27db51f204931532ee288407789a504d17369a4ea2e106846a2f704ca4e64184'
    assert c['original_home_shortfall_bytes']>0 and c['original_had_zero_clean_work'] and c['per_control_cap']==180*2**20
    assert set(c['physical_receipts'])==set(c['durable_archive_catalogs'])=={'off-clean-B','on-clean-B'} and c['native_reruns_after_transport_failure']==0
    for slot,receipt in c['physical_receipts'].items():
        index=c['durable_archive_catalogs'][slot];assert index['native_exit']==receipt['native_exit']==0 and index['slot']==slot
        assert receipt['durable_device']>0 and 0<receipt['size']<=c['per_control_cap']==receipt['source_tmpfs_size']
        raw=(json.dumps(index,sort_keys=True)+'\n').encode();assert hashlib.sha256(raw).hexdigest()==receipt['all_file_index']
        files=index['sha256s'];assert len(files)+1==receipt['all_input_files'] and sum(v[0] for v in files.values())+len(raw)==receipt['input_bytes']<=c['per_control_cap']
        assert all(re.fullmatch('[0-9a-f]{64}',h) and size>=0 and not k.startswith('/') and '..' not in Path(k).parts for k,(size,h) in files.items())
        assert {'runs/'+slot+'/completed.json','runs/'+slot+'/empty-B/cargo.stdout','runs/'+slot+'/empty-B/trace-commit.json','logs/'+slot+'/independent-clean.json','provider/'+slot+'/readback.json'}<=set(files) and len([k for k in files if k.startswith('provider/blobs/')])==5
        assert files['runs/'+slot+'/empty-B/result.json'][1]==p['slots'][slot]['empty-B']['ledgers']['native_terminal']
    assert c['off_previous_transport_guards']['independent_index']==c['physical_receipts']['off-clean-B']['all_file_index']
    assert g['registration']=='924ebea864bdf0dc4a59bf9d4591d6af91ab2d0c9724e1cfbebe44d5749d65be'
    assert g['native_build_dirs']=={'off':'v2-766608715054a316/tikv-jemalloc-sys/e857b49687267b61/out/build','on':'v2-766608715054a316/tikv-jemalloc-sys/409c6d41186d851a/out/build'}
    assert all(not z.get('raw_equal') and not z.get('prior_namespace_only_gate_passed') for z in p['integrated_readback']['cross_flag_elf'].values())
    for rev in 'AB':
        group=g['elfs'][rev]
        if not group['full_reversible_comparison_passed']:continue
        r=group['result']; hashes=[p['slots'][s+'-storage']['return-'+rev]['full_hash'] for s in ('off','on')]
        assert r['original_elf_sha256']==hashes and len(set(hashes))==2
        sec=r['changed_sections'];assert {'.debug_str','.note.gnu.build-id'}<=set(sec)<= {'.debug_info','.debug_macro','.debug_str','.note.gnu.build-id'}
        for name,secrow in sec.items():
            l,z=secrow['a'],secrow['b'];assert all(l[k]==z[k] for k in ['type','offset','size','flags','entsize'])
            if name.startswith('.debug'):assert l['flags']&6==0
            else:assert l['flags']&4==0
        assert len(r['four_load_segments'])==4 and all(v['masked_a']==v['masked_b'] for v in r['four_load_segments'])
        ds=r['complete_decodings']
        for kind in ('info','macro'):
            a,b=ds['P'][kind],ds['Q'][kind]
            assert a['exit']==b['exit']==0 and a['lines']==b['lines']>0 and a['path_replacements']==b['path_replacements']
            assert a['canonical_output_sha256']==b['canonical_output_sha256'] and a['each_65536_lines']==b['each_65536_lines']
        size=p['integrated_readback']['slots']['off-storage']['return-'+rev]['cli']['bytes']
        assert r['outside_allowed_bytes']==size-sum(n for start,n in r['ranges']) and len(r['outside_allowed_sha256'])==64
    raw=gzip.decompress((base/'provider-members.json.gz').read_bytes())
    assert hashlib.sha256(raw).hexdigest()==g['returned_source']['archive-members.json']==g['archives']['member_receipt']
    all_files=json.loads(raw);summaries=g['archives']['complete_five_products'];assert set(all_files)==set(summaries)=={'jemalloc_pic.a','tikv_jemalloc_sys.rmeta','tikv_jemalloc_sys.rlib','tikv_jemallocator.rmeta','tikv_jemallocator.rlib'}
    for name,it in all_files.items():
        from collections import Counter
        bins=Counter();names=headers=0;pending=[];execs=[];alloc=[]
        def inspect(node,address):
            nonlocal names,headers
            cls=node['class'];bins[cls]+=1
            if cls=='identical':assert node['off']==node['on']
            elif cls=='archive':
                assert node['fully_parsed'] and len(node['members'])==max(node['count'])
                for m in node['members']:
                    if 'only' in m:pending.append(address+'/'+str(m['index']));continue
                    hn=[bytes.fromhex(m[k]) for k in ('header_off','header_on')];assert all(len(z)==60 for z in hn)
                    names+=int(m['names'][0]!=m['names'][1]);headers+=int(hn[0]!=hn[1] or m['pad_off']!=m['pad_on'])
                    inspect(m['payload'],address+'/'+m['names'][0])
            else:
                assert node['off']!=node['on']
                if cls=='only_authenticated_nonallocated_debug_path':
                    assert node['debug_path_inverse_ranges'] and not node['executable_differences']
                else:assert cls in ('other_bytes','other_ELF_change');pending.append(address)
                if node.get('executable_differences'):execs.append([address,node['executable_differences']])
                if node.get('allocated_differences'):alloc.append([address,node['allocated_differences']])
        inspect(it,'')
        assert summaries[name]=={'count':dict(bins),'changed_header_or_pad':headers,'changed_member_name':names,'other_payloads':pending,'changed_executable_sections':execs,'changed_allocated_sections':alloc,'off':it['off'],'on':it['on']}
    return {'both_native_cold_receipts':True,'five_archive_or_metadata_inputs_per_mode':len(all_files),'strict_original_cross_option_refusal_retained':True,'full_elf_debug_path_only_by_source':{r:g['elfs'][r]['full_reversible_comparison_passed'] for r in 'AB'}}
def verify_samples(p,base):
    allpaths=set()
    for case,phases in p['slots'].items():
        for tag,r in phases.items():
            path=base/'samples'/(case+'--'+tag+'.tsv.gz');allpaths.add(path)
            b=path.read_bytes(); raw=gzip.decompress(b)
            assert hashlib.sha256(b).hexdigest()==r['ledgers']['whole_sampling'] and hashlib.sha256(raw).hexdigest()==r['sample_raw_sha256']
            vals=[tuple(map(int,v.split())) for v in raw.splitlines()]
            assert len(vals)==r['samples'] and vals[0]==(0,r['sample_start']) and vals[-1][1]==r['sample_end'] and max(v[1] for v in vals)==r['peak']
            gaps=sorted(z[0]-v[0] for v,z in zip(vals,vals[1:]));assert min(gaps)>0
            assert r['gap_ns']=={'min':min(gaps),'median':statistics.median(gaps),'p99':gaps[int(.99*(len(gaps)-1))],'max':max(gaps)}
    assert set((base/'samples').iterdir())==allpaths
    return len(allpaths)
if __name__=='__main__':
    p=json.loads(Path(sys.argv[1]).read_bytes());print(json.dumps({'deltas':check(p),'all_raw_sample_streams':verify_samples(p,Path(sys.argv[1]).parent),'separate_native_and_debug':verify_diagnostic(p,Path(sys.argv[1]).parent),'rejected_mutations':negatives(p)},indent=2))
