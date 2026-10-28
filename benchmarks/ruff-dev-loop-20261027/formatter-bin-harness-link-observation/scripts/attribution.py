"""Join stock Wild's real layout against the actual archive's member boundaries."""
from pathlib import Path
from runpy import run_path
from collections import Counter
import sys, json, hashlib
p=Path(__file__).resolve().parent; api=run_path(str(p/'linked-layout.py'));store=p/'runs-v2'
sha=lambda b:hashlib.sha256(b).hexdigest()
def fingerprint(keys):
    return sha(json.dumps(keys,sort_keys=True,separators=(',',':')).encode())
result={}; details={}; libs={}
for phase in ['prime','edit','restore','observing-main','observing-edit','observing-restore']:
    d=store/phase;r=json.loads((d/'row.json').read_bytes());m,idx=api['archive']((d/'formatter.rlib').read_bytes());libs[phase]=(m,idx)
    diag=[]
    for key,(raw_name,start,end,payload) in m.items():
        if not key.endswith('.o'):continue
        for brand in [b'internal Rome error.',b'internal Ruff error.']:
            if brand not in payload:continue
            di=api['elf'](payload)[0]; diag.append({'member':key,'raw_name':raw_name,'byte_marker':brand.decode(),'strings':payload.count(brand),'sections':[s for s in di if 'FormatError' in s and 'fmt' in s][:6]})
    native=json.loads((d/'native.json').read_bytes());links={}
    for f in sorted(d.glob('*.layout')):
        l,=[v for v in native['links'] if Path(v['output']).name==f.name[:-7]]
        files,metrics=api['decode_layout'](f.read_bytes());selected={}
        for path,ent,sections,tmp in files:
            member_archive=Path(path).name
            if not member_archive.startswith('libruff_formatter-'):continue
            assert ent and not tmp
            start,end,name=ent;key=api['stable'](name)
            rn,st,en,b=m[key]
            assert (rn,st,en)==(name,start,end)
            secs,syms=api['elf'](b)
            assert len(secs)==len(sections)
            selected[key]={'retained_sections':sum(v is not None for v in sections),'allocated':sum(s[1]-s[0] for s in sections if s is not None),'retained_fmt':[(k,sections[v[0]]) for k,v in secs.items() if sections[v[0]] is not None and 'FormatError' in k and 'fmt' in k][:10]}
        a=l['argv']; arch,=[(i,Path(x).name) for i,x in enumerate(a) if Path(x).name.startswith('libruff_formatter-') and x.endswith('.rlib')]
        links[f.name[:-7]]={'total_selected_files':len(files),'formatter_member_count':len(selected),'members':selected,'selected_formatter_sections':sum(x['retained_sections'] for x in selected.values()),'selected_marker':[x['member'] for x in diag if x['member'] in selected],'format_monomorphizations':{k:v['retained_fmt'] for k,v in selected.items() if v['retained_fmt']},'thunks':metrics,'wild_arguments':len(a),'rlibs':sum(x.endswith('.rlib') for x in a),'formatter_operand_index':arch[0],'argv_sha':l['raw'],'layout_sha':sha(f.read_bytes()),'stock_elf':next(v['elf'] for v in r['wilds'] if v['name']==f.name[:-7])}
        details[f'{phase}/{f.name}']=selected
    cache=json.loads((d/'harness.rlink-cache.json').read_bytes()); dep=json.loads((d/'test-bin-ruff_python_formatter.json').read_bytes())
    result[phase]={'native':links,'raw_elf':r['bin_sha'],'rlink':r['bin_rlink'],'rlink_cache_keys':list(cache),'fingerprint_keys':list(dep),'source_diagnostics':r['source_diagnostics_sha'],'bin_source':r['source_bin_root_sha'],'objects':r['objects'],'formatter_archive':r['formatter_archive'],'index_entries':len(idx),'index_canonical':fingerprint(idx),'exact_member_order':fingerprint([v[0] for v in m.values()]),'cgus':len([k for k in m if k.endswith('.o')]),'archive_marker':diag,'harness_list':r['harness_list'],'observed':r['observed'],'cli_sha':r['cli_sha']}
compare={}
for a,b in [('prime','edit'),('edit','restore'),('observing-edit','observing-restore')]:
    ma,ia=libs[a];mb,ib=libs[b];common=[k for k in ma if k in mb and k.endswith('.o')]
    changed=[k for k in common if ma[k][3]!=mb[k][3]]
    compare[f'{a} vs {b}']={'same_exact_member_order':[v[0] for v in ma.values()]==[v[0] for v in mb.values()],'same_semantically_matched_order':list(ma)==list(mb),'same_ordered_normalized_symbol_index':ia==ib,'cgus_common':len(common),'cgus_name_change':sum(ma[k][0]!=mb[k][0] for k in common),'changed_payload':changed,'raw_rmeta_equal':ma.get('lib.rmeta',[None]*4)[3]==mb.get('lib.rmeta',[None]*4)[3],'same_harness_rcgus':result[a]['objects']==result[b]['objects'],'exact_rlink_equal':result[a]['rlink']==result[b]['rlink']}
(p/'attribution.json').write_text(json.dumps({'phases':result,'comparison':compare},sort_keys=True,indent=2)+'\n')
for phase,v in result.items():
    print(phase,[(k,z['formatter_member_count'],z['selected_formatter_sections'],len(z['selected_marker'])) for k,z in v['native'].items()],len(v['archive_marker']),v['index_entries'],v['harness_list'].strip(),(v['observed'] or '')[0:35],flush=True)
print('sums',[(k,{a:(len(vv) if isinstance(vv,list) else vv) for a,vv in v.items()}) for k,v in compare.items()],flush=True)
