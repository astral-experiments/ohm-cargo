#!/usr/bin/env python3
"""Verify the public process projection. With --self-test, corrupt six independent observations."""
import argparse,collections,copy,gzip,hashlib,json,re
from pathlib import Path
ARMS=['C-7277','W-7277','W-K']
PHASES=['01-empty','02-first-unchanged','03-second-unchanged']
EXPECTED={'C-7277':(74,503,71,21),'W-7277':(119,433,103,53),'W-K':(107,470,103,53)}
C='960c75a231a4bed61cb9fcfac744ea37161ea23d';W='ad005f99d0b51fd62b5c237bc13b31b371a1686e'
REL='7277e6cdaba44c43294a07c0661fc8e69fd8e3e7';K='84af87848a5a952ba61ae6a2cc5b22da24130200'
WILD='0d6335808b647d499f3d74993b602e64ff0625206c809bf4913c487eea380cd5'
HD=lambda s:bool(re.fullmatch(r'[a-f0-9]{64}',s))
def unit(r):return (r['package'],r['kind'],r['target'],r['unit'],r['metadata'],r['test_harness'],r['rustc_kind'],tuple(r['features']))
def verify(r):
    assert r['schema']==1 and r['phases']==PHASES and set(r['arms'])==set(ARMS)
    source=r['source'];assert [(source[a]['rust'],source[a]['cargo']) for a in ARMS]==[(C,REL),(W,REL),(W,K)]
    assert {source[a]['common_source'] for a in ARMS}=={'93526150df078af7dd8fc4226cdcc469539d2001'}
    assert len({source[a]['common_lock'] for a in ARMS})==len({source[a]['fixed_list_sha'] for a in ARMS})==1
    assert source[ARMS[0]]['cargo_sha256']==source[ARMS[1]]['cargo_sha256']!=source[ARMS[2]]['cargo_sha256']
    assert source[ARMS[0]]['driver_sha256']!=source[ARMS[1]]['driver_sha256']==source[ARMS[2]]['driver_sha256']
    assert r['parent_receipts']['release_third']=='35171c6a4565a7b9f9535f4993aa015971de2914329e8a6067e506bf37fe0551' and r['parent_receipts']['ancestor_pair']=='e34c5e06a908cbac67f9159e358b9a765207d56e481165e971308b897b16bb82'
    assert all(HD(v) for v in r['parent_receipts'].values());seed=None;typed=set();details={};work={};native={};elf_sets=collections.defaultdict(set);lists=collections.defaultdict(set)
    for a in ARMS:
        work[a]={};native[a]={}
        for ix,s in enumerate(PHASES):
            v=r['arms'][a][s];rs=v['compiler'];ns=v['native'];fs=v['fixed'];counts=v['role_counts'];rec=r['receipts'][a][s]
            assert all(HD(h) for k,h in rec.items() if k!='n_pid_files') and rec['n_pid_files']>=max(len(rs),len(ns))
            assert v['typed']==619 and len(rs)==(623 if not ix else EXPECTED[a][0]) and v['fresh']==(0 if not ix else EXPECTED[a][1])
            assert counts.get('rustc-cached',0)==0 and all(j['rustc_kind']=='rustc-full' and HD(j['physical_argv_sha256']) for j in rs);assert len(v['rustc_target_info_probes'])==(1 if not ix else 0) and counts['rustc-full']==len(rs)+len(v['rustc_target_info_probes'])
            assert len(ns)==counts['wild']==(188 if not ix else EXPECTED[a][2]) and len({q['argv_sha256'] for q in ns})==len(ns)
            assert counts['collect2']>=len(ns) and counts['gcc']>=len(ns) and v['physical_images']['wild']==[WILD] and v['physical_images']['cargo']==[source[a]['cargo_sha256']]
            fixed={q['fixed'] for q in ns if q['fixed']};assert len(fixed)==50==len(fs) and fixed==set(fs) and all(t['stock_link'] for t in fs.values()) and sum(q['fixed'] is None for q in ns)==(138 if not ix else EXPECTED[a][3])
            seed=sorted(fixed) if seed is None else seed;assert seed==sorted(fixed)
            for q in ns:
                assert HD(q['argv_sha256']) and HD(q['out_sha256']) and '/' not in q['leaf'] and q['leaf']
                if q['fixed']:assert q['leaf']==fs[q['fixed']]['actual']
            for n,df in fs.items():
                assert HD(df['elf']) and HD(df['list']) and df['bytes']>0;elf_sets[n].add(df['elf']);lists[n].add(df['list'])
            e=fs['ty_server/test/e2e'];assert e['tests']==200 and e['list']=='76d24b892727ff181fdf019636ef5e928d741eb8df4f58f06dcc626d0bf67c52' and e['elf']=='6ffb1206ae1ffd7de9e7e335abf8ce07dd9e37c940c6039488c220cf3868b06e'
            typed.add(v['typed_identity'])
            if ix:
                for j in rs:assert j['package'] and j['kind'] and j['target'] and len(j['unit'])==16 and all(c in '0123456789abcdef' for c in j['unit'])
                work[a][s]=collections.Counter(map(unit,rs));native[a][s]=collections.Counter((q['leaf'],q['unit'],q['fixed']) for q in ns)
        assert work[a][PHASES[1]]==work[a][PHASES[2]] and native[a][PHASES[1]]==native[a][PHASES[2]]
    assert len(typed)==1 and all(len(h)==1 for h in lists.values())
    diff=work['W-7277'][PHASES[1]]-work['W-K'][PHASES[1]];reverse=work['W-K'][PHASES[1]]-work['W-7277'][PHASES[1]]
    assert sum(diff.values())==12 and not reverse and native['W-K'][PHASES[1]]==native['W-7277'][PHASES[1]]
    crates=collections.Counter(k[0] for k in diff.elements());assert crates==collections.Counter(['chacha20','chacha20','compact_str','ruff_graph','ruff_python_ast','rustix','tempfile','terminal_size','ty_ide','ty_module_resolver','ty_python_semantic','zmij'])
    assert all(k[1]=='lib' and not k[5] for k in diff);assert {k[3] for k in diff if k[0]=='chacha20'}=={'57ca8d8aebf28f0c','7cd6cc545721f6f6'}
    observed={k:v for k,v in elf_sets.items() if len(v)>1}
    assert set(observed)==set(r['sections'])=={'ruff/bin/ruff','ty/bin/ty','ty_python_semantic/lib/ty_python_semantic'}
    for k,vs in observed.items():
        cmp,=r['sections'][k];assert vs=={cmp['a'],cmp['b']} and cmp['text_exact'] and cmp['rodata_exact'] and cmp['all_loads_after_only_buildid_mask'] and cmp['allocated_content_differences']==['.note.gnu.build-id']
    return {'source':[(source[a]['rust'][:12],source[a]['cargo'][:12]) for a in ARMS],'nine_visits':9,'each_empty':[619,0,623,1,188,50],'unchanged_full_fresh_wild_extra':EXPECTED,'repeats_each':2,'compiler_jobs_saved_by_K':[{'package':k[0],'target':k[2],'unit':k[3],'metadata':k[4],'features':k[7]} for k in sorted(diff.elements())],'native_jobs_differ_between_W_arms':False,'three_disclosed_ELF_exceptions':sorted(observed),'fixed_native_targets':seed}
def negatives(r):
    def remove_link(v):v['arms']['W-K'][PHASES[1]]['native'].pop()
    def fake_cheap(v):v['arms']['W-7277'][PHASES[1]]['compiler'].pop()
    def hide_chacha(v):
        for p in PHASES[1:]:
            c=[j for j in v['arms']['W-7277'][p]['compiler'] if j['package']=='chacha20'];assert len(c)==2;c[0]['unit']=c[1]['unit']
    def change_rust(v):v['source']['W-7277']['rust']=C
    def change_output(v):v['arms']['C-7277'][PHASES[0]]['fixed']['ty_server/test/e2e']['elf']='1'*64
    def fake_sections(v):v['sections']['ruff/bin/ruff'][0]['rodata_exact']=False
    for f in [remove_link,fake_cheap,hide_chacha,change_rust,change_output,fake_sections]:
        b=copy.deepcopy(r);f(b)
        try:verify(b)
        except AssertionError:pass
        else:raise RuntimeError(f.__name__+' was accepted')
if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--self-test',action='store_true');ap.add_argument('--input',type=Path,default=Path(__file__).parent/'observations.json.gz');a=ap.parse_args();data=json.load(gzip.open(a.input));v=verify(data)
    if a.self_test:negatives(data)
    print(json.dumps(v,indent=2,sort_keys=True))
