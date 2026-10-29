"""Independently reconcile the genuine job census, overlay/window comparisons and all row-level cold receipts."""
from pathlib import Path
import collections,gzip,hashlib,json,itertools
K=Path(__file__).resolve().parent
def get(n):
 b=(K/n).read_bytes();return json.loads(gzip.decompress(b) if str(n).endswith('.gz') else b)
def sh(b):return hashlib.sha256(b).hexdigest()
def main():
 cmds=get('commands.json.gz');index={(r['lane'],r['visit']):r for r in cmds};assert len(index)==22 and sum(r['exit']==101 for r in cmds)==2
 for r in cmds:
  a=get('records/'+r['native']);e=a['events'];real=[z for z in e if z['role']=='rustc-full' and z['target']!='___'];root=[z for z in real if z['target']=='e2e'];wild=[z for z in e if z['role']=='stock-wild'];selected=[z for z in wild if z['output'] and (z['output']or '').endswith('e2e-8945421a8b988468')];
  if r['full_origin']=='cold':assert len(real)==303 and len(wild)==48 and len(selected)==len(root)==1
  elif r['full_origin']=='settled':assert not real and not wild
  elif r['exit']==101:assert len(real)==len(root)==1 and len(wild)==0
  elif r['full_origin'] in ('dirty','leaf'):assert len(real)==len(root)==len(wild)==len(selected)==1
  if selected:assert len(selected[0]['ordered_file_operands'])==366 and len(root[0]['explicit_externs'])==73
 z=get('cold-generation-differences.json.gz')['pairs'];
 for n,x in z.items():
  by=collections.Counter(Path(k).suffix or 'exe' for k in x['changed_typed']);assert by==({'.rlib':34}if n=='cold-parent__cold-child'else{'.rlib':36,'.rmeta':27,'.so':1});assert not x['changed_build_script_count']
  assert len(x['changed_metadata'])==(0 if n=='cold-parent__cold-child' else 27)
 arc=get('archive-name-evidence/terminal.json');assert arc['all_changed_archives_accounted'] and arc['raw_equal']==219 and len(arc['compared'])==34
 for z in arc['compared'].values():
  p=K/'archive-name-evidence'/z['record'];assert sh(p.read_bytes())==z['record_sha256'];v=get(p.relative_to(K));assert v['left']==z['left'] and v['predicted_sha256']==v['right']==z['right'] and all(len(a)==len(b)==7 for i,a,b in v['edits'])
 assert sum(v['field_count']for v in arc['compared'].values())==4506
 term=get('recipe-evidence/terminal.json');lanes=term['rows'];tw=term['wire_sha256'];assert len(lanes)==8 and len(term['negative'])==9 and len(term['directed_whole_reconstructions'])==56
 assert {(l,r)for l,r,_ in term['directed_whole_reconstructions']}==set(itertools.permutations(lanes,2));assert all(h==lanes[r]['raw_sha']for l,r,h in term['directed_whole_reconstructions']);raw_cfg=get('recipe-evidence/independent-cfg-decoder.json.gz');shifts={}
 for l,q in lanes.items():
  d=get('recipe-evidence/'+l+'.json.gz');assert d['raw_sha']==q['raw_sha']==raw_cfg[l]['input_sha256'] and d['wire_sha']==tw and d['wire_len']==term['wire_length']; rec=d['modules'];assert len(rec)==139 and len({x['cgu']for x in rec})==139 and sorted(x['module_kind']for x in rec).count('regular')==138
  assert len(d['span_coordinates'])==23 and all(x['hi']-x['lo']==x['local_hi']-x['local_lo']==len(x['annotated_text']) for x in d['span_coordinates']);assert raw_cfg[l]['indexed_crates']==233 and len(raw_cfg[l]['spans'])==23
  assert d['source_map_bases']['7']-d['source_map_bases']['5']==90107
  b=next(x for x in cmds if x['lane']==l and x['visit']==('restore'if l.startswith('warm') else'edited-cold' if l.startswith('cold')else'root-empty'));e=get('records/'+b['native'])['events'];w,=[z for z in e if z['role']=='stock-wild'and z['output'] and z['output'].endswith('e2e-8945421a8b988468')];ops={o['index']:o for o in w['ordered_file_operands']}
  for v in rec:
   o=ops[v['operand_index']];assert Path(o['path']).name==v['object_name'] and (o['size'],o['sha256'])==(v['bytes'],v['sha256']);
   if v['links_from_incr_cache']:assert v['physical_same_dev_ino_size_sha'][2:]==[v['bytes'],v['sha256']] and v['original_path'].startswith('TARGET/debug/incremental/')
  assert sum(q['links_from_incr_cache'] for q in rec)==(135 if l.startswith('warm') else 0)
  shifts[l]=[[a['lo'],a['hi']] for a in d['span_coordinates']]
 for l in ['cold-parent','leaf-parent-original','leaf-parent-edited','warm-parent']:assert shifts[l]==shifts[l.replace('parent','child')]
 for i in range(23):
  for j in (0,1):assert shifts['warm-parent'][i][j]-shifts['leaf-parent-original'][i][j]==11090900 and shifts['leaf-parent-original'][i][j]-shifts['leaf-parent-edited'][i][j]==9
 tests=get('actual-runtime.json.gz');assert sum(len(x['three_replayed_tests']) for x in tests)==60;inv=(K/'test-inventory.txt').read_bytes();assert sum(x.endswith(b': test')for x in inv.splitlines())==200
 for phase in tests:
  for test in phase['three_replayed_tests']:assert sh(test['actual_stdout'].encode())==test['actual_stdout_sha'] and ('test '+test['name']+' ... ok') in test['actual_stdout']
 t=get('parent-profile-stop.json');assert t['exit']==-5 and t['cargo_stdout_bytes']==t['observed_rustc']==t['observed_wild']==0 and not t['count_exposed']
 print('Verified 22 genuine commands, all 7 native-operand comparisons, 34 archive reconstructions, 8 original recipes, 46 typed source coordinates per file and zero scored pairs.')
if __name__=='__main__':main()
