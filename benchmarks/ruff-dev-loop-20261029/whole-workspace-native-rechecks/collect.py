#!/usr/bin/env python3
"""Project the preserved Cargo JSON, physical process rows and native ELF checks into a path-free comparison."""
import argparse,collections,gzip,hashlib,json,re
from pathlib import Path
def digest(p):
    with p.open('rb') as fp:return hashlib.file_digest(fp,'sha256').hexdigest()
def read(p):return json.loads(p.read_bytes())
def project(old, release, dest):
    sha=lambda b:hashlib.sha256(b).hexdigest()
    zipped=lambda p:json.load(gzip.open(p))
    head={'C-7277':old/'C','W-7277':release/'W','W-K':old/'W'}; stages=['01-empty','02-first-unchanged','03-second-unchanged']
    bindings={};cases={};receipts={};elist={}
    for arm,root in head.items():
        base=root/'evidence';binding=read(base/'binding.json');env=binding['environment']
        bindings[arm]={'rust':binding['driver_source'],'cargo':binding['cargo_source'],'driver_sha256':next(iter(binding['driver'].values())),'cargo_sha256':binding['cargo_sha256'],'common_source':binding['source_head'],'common_tree':binding['source_tree'],'common_lock':binding['worktree_lock'],'sdk_manifest':binding['rust_product_sha256'],'binding':digest(base/'binding.json'),'fixed_list_sha':binding['historical']}
        view=Path(env['CARGO_TARGET_DIR']).parent;src=view/'source';cases[arm]={};receipts[arm]={}
        for ix,label in enumerate(stages):
            case=base/label;completion=read(case/'complete.json');assert digest(case/'cargo.stdout')==completion['cargo']['stdout'] and digest(case/'cargo.stderr')==completion['cargo']['stderr']
            native=zipped(case/'native-jobs.json.gz');assert digest(case/'native-jobs.json.gz')==completion['native']['native_jobs']
            arts=[r for r in map(json.loads,(case/'cargo.stdout').read_bytes().splitlines()) if r['reason']=='compiler-artifact'];native_counts=collections.Counter(j['kind'] for j in native);assert native_counts==completion['native']['counts']
            def crate_arg(a,k):return a[a.index(k)+1] if k in a else None
            def sourcepath(a):
                n=[x for x in a if x.endswith('.rs')]
                return (src/Path(n[0])).absolute() if len(n)==1 else None
            def unitcode(a):
                extra=next((s.removeprefix('extra-filename=') for s in a if s.startswith('extra-filename=')),'');meta=next((s.removeprefix('metadata=') for s in a if s.startswith('metadata=')),'');out=crate_arg(a,'--out-dir');uid=Path(out).parent.name if out else ''
                return extra.lstrip('-'),meta,uid
            def select(j):
                a=j['args'];cn=crate_arg(a,'--crate-name');rawsrc=sourcepath(a);types=crate_arg(a,'--crate-type');test='--test' in a;extra,meta,uid=unitcode(a);out=crate_arg(a,'--out-dir')
                value={'crate':cn,'test_harness':test,'crate_type':types,'unit':uid,'extra_filename':extra,'metadata':meta,'features':sorted(a[i+1][9:-1] for i,x in enumerate(a[:-1]) if x=='--cfg' and a[i+1].startswith('feature="')),'physical_argv_sha256':j['argv_sha256'],'rustc_kind':j['kind']}
                if ix:
                    co=[x for x in arts if x['target']['src_path']==str(rawsrc) and x['target']['name'].replace('-','_')==cn]
                    alt=[x for x in co if any(Path(f).parent==Path(out) for f in x['filenames'])]
                    if alt:co=alt
                    if len(co)>1:co=[x for x in co if x['profile']['test']==test]
                    assert len(co)==1,(cn,uid,len(co))
                    row,=co;t=row['target'];assert not row['fresh'];pkg=Path(out).parts[-3]
                    value.update(package=pkg,kind=','.join(t['kind']),target=t['name'],cargo_test=row['profile']['test'],workspace=rawsrc.is_relative_to(src))
                return value
            rs=[];probes=[]
            for j in native:
                if j['kind'] not in ('rustc-full','rustc-cached'):continue
                a=j['args']
                if (any(s=='--print' or s.startswith('--print=') for s in a) and not any(s=='--emit' or s.startswith('--emit=') for s in a)):probes.append(j['argv_sha256']);continue
                rs.append(select(j))
            bpid={j['tid']:j for j in native if j['kind']=='wild'};fixed={};tag={}
            for k,t in completion['selected'].items():
                w=t['native']['wild'];assert len(w)==len(t['native']['gcc'])==len(t['native']['collect2']) and len(w)<=1
                if w:pid=w[0]['tid'];assert pid in bpid and pid not in tag and w[0]['argv_sha256']==bpid[pid]['argv_sha256'];tag[pid]=k
                fixed[k]={'actual':t['actual_basename'],'elf':t['sha256'],'bytes':t['bytes'],'tests':t['listed_tests'],'list':t['list_sha256'],'stock_link':bool(w)}
                assert digest(case/t['list_file'])==t['list_sha256']
                if k=='ty_server/test/e2e':
                    for idx,exact in enumerate(['inlay_hints::default_inlay_hints','notebook::hover_past_end_of_cell','notebook::inlay_hints_range_past_end_of_cell']):
                        assert ('test '+exact+' ... ok') in (case/t['list_file']).parent.joinpath('case-'+str(idx)+'.stdout').read_text().splitlines()
            current=[]
            for ti,r in bpid.items():
                a=r['args'];out=Path(r['output']);assert a[a.index('-o')+1]==str(out)
                links=[i for i,s in enumerate(a) if s.startswith('-L') and 'psm' in Path(s[2:]).parts and Path(s[2:]).name=='out'];gcc=[i for i,s in enumerate(a) if s=='-lgcc_s']
                current.append({'leaf':out.name,'unit':out.parent.parent.name if re.fullmatch('[a-f0-9]{16}',out.parent.parent.name) else None,'fixed':tag.get(ti),'shared':('-shared' in a or '--shared' in a),'earlier_psm_before_gcc_s':bool(links and gcc and links[0]<gcc[0]),'out_sha256':sha(str(out).encode()),'argv_sha256':r['argv_sha256']})
            assert len(current)==native_counts['wild'] and len(rs)==completion['actual_full_rustc'] and len(probes)==completion['target_probes']
            images={role:sorted({completion['native']['images'][j['path']]['sha256'] for j in native if j['kind']==role}) for role in ['cargo','cargo-proxy','rustc-full','gcc','collect2','wild']}
            cases[arm][label]={'typed':len(arts),'fresh':sum(x['fresh'] for x in arts),'typed_identity':completion['typed_sha256'],'compiler':sorted(rs,key=lambda v:(v['crate'],v['unit'],v['physical_argv_sha256'])),'rustc_target_info_probes':probes,'native':sorted(current,key=lambda v:(v['leaf'],v['out_sha256'])),'fixed':fixed,'role_counts':dict(native_counts),'physical_images':images}
            receipts[arm][label]={'cargo_stdout':completion['cargo']['stdout'],'cargo_stderr':completion['cargo']['stderr'],'physical_jobs':digest(case/'native-jobs.json.gz'),'pid_tree':completion['native']['raw_sha256'],'n_pid_files':completion['native']['raw_pid_files'],'completed':digest(case/'complete.json')}
    layouts=read(release/'native-elf-scope.json');tr=read(release/'terminal.json')
    for k,cs in layouts['native_comparisons'].items():
        elist[k]=[{'a':r['a'],'b':r['b'],'differing_sections':r['different_fields'],'allocated_content_differences':r['different_allocated_bytes'],'text_exact':r['text'],'rodata_exact':r['rodata'],'all_loads_after_only_buildid_mask':r['load_match_after_build_id_only'],'program_headers_identical':r['program_header_table_equal']} for r in cs]
    object={'schema':1,'source':bindings,'phases':stages,'arms':cases,'receipts':receipts,'sections':elist,'parent_receipts':{'ancestor_pair':digest(old/'terminal.json'),'ancestor_comparison':digest(old/'comparison.json'),'release_third':digest(release/'terminal.json'),'release_by_target':tr['target_table'],'release_ELF_bodies':tr['body_table'],'three_arm_ELF_sections':digest(release/'native-elf-scope.json')}}
    dest.mkdir(parents=True,exist_ok=True);p=dest/'observations.json.gz';b=json.dumps(object,sort_keys=True,separators=(',',':')).encode()+b'\n'
    with p.open('xb') as out,gzip.GzipFile(fileobj=out,mode='wb',mtime=0,filename='') as fp:fp.write(b)
    print(digest(p),len(b),p.stat().st_size)
if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--earlier-two-arm',type=Path,required=True);ap.add_argument('--new-release-arm',type=Path,required=True);ap.add_argument('--out',type=Path,required=True);a=ap.parse_args();project(a.earlier_two_arm,a.new_release_arm,a.out)
