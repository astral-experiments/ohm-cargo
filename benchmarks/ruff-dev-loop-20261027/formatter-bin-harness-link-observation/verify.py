"""Verify the formatter harness native observations from independently exported process and archive rows."""
from pathlib import Path
from collections import Counter
import gzip, hashlib, json, re
p=Path(__file__).resolve().parent
digest=lambda b:hashlib.sha256(b).hexdigest()
def load(name):
    file=p/(name+'.json.gz')
    return json.loads(gzip.decompress(file.read_bytes()))
old=load('original-run');work=load('independent-workspace');layout=load('stock-layout-attribution');archive=load('archive-members-and-index');native=load('native-controls');selector=load('selector-runs')
h='ruff_python_formatter-81814697f8234e3f';lib='libruff_formatter-ec58abd591816f64.rlib'
ident='ce80372dd5924bba1bf4639ac1b8d8e92f809540d614ca98fb54fa20f56d783d'
assert all(n['units']==218 and n['typed_harness']['target']['kind']==['bin'] and n['typed_harness']['profile']['test'] and n['tracked_bin_and_dep'][h]['raw_elf_or_rlib_sha']==ident for n in old.values())
for mode in ('edit','restore'):
    o=old[mode];assert o['physical']=={'full':1,'link-only':4} and o['wild']==4
    records=o['processes'];link,=records['links'];assert len(link['argv'])==195 and sum(v.endswith('.rlib') for v in link['argv'])==135
    assert sum(Path(v).name==lib for v in link['argv'])==1 and any(v.endswith('.rlink') for v in records['jobs'][0]['argv'])
    assert records['jobs'][0]['kind']=='link-only' and records['jobs'][0]['exit']==0
assert len({old[z]['tracked_bin_and_dep'][lib]['raw_elf_or_rlib_sha'] for z in ('settle2','edit','restore')})==3
assert all('unused-externs' not in x for x in old['cold']['processes']['jobs'][0]['argv'])
assert all(work[name]['row']['units']==218 for name in work)
assert work['prime']['row']['fresh']==218 and not work['prime']['row']['rustc']
for x,y,observer in [('edit','restore',False),('observing-edit','observing-restore',True)]:
    m,n=archive[x],archive[y]
    assert len(m['ordered_symbols'])==len(n['ordered_symbols'])==544
    assert [(s,ndx) for s,_,ndx in m['ordered_symbols']]==[(s,ndx) for s,_,ndx in n['ordered_symbols']]
    left={k:(i,size,sha) for i,k,size,sha in m['members']};right={k:(i,size,sha) for i,k,size,sha in n['members']}
    assert left.keys()==right.keys() and left['lib.rmeta'][2]!=right['lib.rmeta'][2]
    objects=[k for k in left if k.endswith('.o')];assert len(objects)==50
    assert sum(left[k][0]!=right[k][0] for k in objects)==50
    assert sum(left[k][2]!=right[k][2] for k in objects)==1
    a,b=work[x]['row'],work[y]['row']
    assert a['objects']==b['objects'] and len(a['objects'])==(5 if observer else 4) and a['bin_rlink']==b['bin_rlink'] and work[x]['raw_rlink']==a['bin_rlink']==work[y]['raw_rlink']
    assert (a['bin_sha']!=b['bin_sha'])==observer
    for stage in (x,y):
        w=work[stage];la=layout['phases'][stage];r=w['row']
        assert r['rustc']=={'full':1,'link-only':4} and len(r['wilds'])==4 and r['fresh']==211
        assert w['rlink_manifest']['version']==5 and 'unused_extern_names' not in w['rlink_manifest']
        ld=la['native'][h];assert ld['rlibs']==135 and ld['wild_arguments']==(196 if observer else 195)
        assert ld['formatter_member_count']==(50 if observer else 0)
        assert ld['selected_formatter_sections']==(24 if observer else 0)
        assert len(ld['selected_marker'])==int(observer)
        for name,link in la['native'].items():
            if name!=h:assert link['formatter_member_count']==50 and len(link['selected_marker'])==1
        if observer:assert ('internal '+('Rome' if stage.endswith('edit') else 'Ruff')+' error.') in r['observed']
        else:assert r['harness_list']=='0 tests, 0 benchmarks\n' and r['bin_sha']==ident
    assert a['cli_sha']!=b['cli_sha']
for variant in ('shadow-v2','shadow-default'):
    orig,edit,restored=[native[variant]['phases'][key]['row'] for key in ('original','edited-shadow','restored')]
    assert [r['run_status'] for r in [orig,edit,restored]]==[0,83,0]
    assert orig['elf']==restored['elf']==ident!=edit['elf']
    assert orig['obj_inputs']==edit['obj_inputs']==restored['obj_inputs'] and orig['rlink']==edit['rlink']==restored['rlink']
    for r in (edit,restored):
        assert r['rustc']=={'full':1,'link-only':4} and r['wilds']==4 and r['harness_job']=='link-only'
    if variant=='shadow-v2':assert edit['selected_formatter_members']==restored['selected_formatter_members']==0 and edit['selected_probe_object'] and not restored['selected_probe_object']
    else:assert not edit['layout_request']
    opens=[l for proc,l in edit['actual_open'] if proc in edit['wild_family'] and re.search(r'= [0-9]+$',l)]
    assert any(edit['native_library'] in l for l in opens) and any('/force.o"' in l for l in opens)
assert native['shadow-v2']['phases']['edited-shadow']['row']['elf']==native['shadow-default']['phases']['edited-shadow']['row']['elf']
pro=native['provider']['phases']
assert [pro[k]['row']['harness_status'] for k in ('ordinary','provider','restored')]==[0,83,0]
assert [pro[k]['row']['harness_rustc'] for k in ('ordinary','provider','restored')]==['full','full','full']
assert pro['provider']['row']['rustc']=={'full':7} and ' T write' in pro['provider']['row']['write_symbol'][0]
assert pro['ordinary']['row']['raw_elf']==pro['restored']['row']['raw_elf']==ident
for kind,expected in [('previous-empty',([41]*4,[0]*4,0)),('forced-symbol',([42,41,41,42],[256,0,0,256],50)),('whole-archive',([42,41,41,42],[256,0,0,256],52))]:
    rr=[selector[kind+':'+s] for s in ('prime','edit','restore','repeat-prime')]
    assert [r['status'] for r in rr]==expected[0] and [r['matched_bytes'] for r in rr]==expected[1]
    assert {r['selected_archive_members'] for r in rr}=={expected[2]} and len({r['argv_sha'] for r in rr})==1 and len({r['script'] for r in rr})==len({r['object'] for r in rr})==1 and rr[0]['elf']==rr[-1]['elf']
    assert all(r['input_section_bytes']==243 for r in rr)
print('Verified the original 218-unit rosters, six independent workspace phases, four native terminal kinds, three ordinary Cargo control sequences, and 12 stock Wild selectors.')
