"""Independently verify all four cold histories, the original rejection and the four debug pairs."""
from collections import Counter
from itertools import combinations
from pathlib import Path
import base64,gzip,hashlib,io,json,re,subprocess,sys,tarfile
root=Path(__file__).resolve().parent;sys.path.insert(0,str(root));H=lambda b:hashlib.sha256(b).hexdigest()
def get(n):return json.loads((root/n).read_bytes())
deny=re.compile(rb'openai[.](org|com|internal)|artifactory[.]|authoriz'+rb'ation: bearer|github_'+rb'pat_|ghp_[A-Za-z0-9]{16}',re.I)
ledger=json.loads(gzip.decompress((root/'physical-original-sha256.json.gz').read_bytes()))
native=get('diagnostic-private--structural.json');fields=get('diagnostic-private--dwarf-debug.json')
term=get('terminal-summary.json');assert term['no_score_launch']and term['no_qualified']and term['no_wall']and term['literal_exit']==term['typed_exit']=='1'
assert b"'guards']"in (root/'launch-train--stderr').read_bytes()and b"'roster'"in(root/'launch-audit--stderr').read_bytes()
canonical=lambda v:json.dumps(v,sort_keys=True,separators=(',',':')).encode()
counts={};records={};unitroots=set()
for file in sorted(root.glob('records-*.tar.gz')):
 k=file.name[len('records-'):-len('.tar.gz')];counts[k]={}
 with tarfile.open(file)as t:m={r.name:t.extractfile(r).read()for r in t if r.isfile()}
 for n,d in m.items():
  assert ledger[n][1]==H(d)and ledger[n][3]==len(d)and not deny.search(d)
 for tag in ('cold','transitional','qual-1','qual-2'):
  pref=f'receipts/{k}/{tag}/';j=lambda n:json.loads(m[pref+n]);row=j('result.json');phys=j('processes.json');ro=j('roster.json');cmd=j('binding.json')
  assert len(ro['units'])==619 and len(ro['executables'])==102 and len(row['products'])==110 and row['guards']['harness_profile']==84 and row['guards']['nonharness_profile']==18
  assert row['status']==0 and row['command']==['cargo','+ohm','test','--no-run','--workspace','--locked','--offline','-j4','--message-format=json']
  assert row['physical']==ledger[pref+'processes.json'][0]and row['stdout']==ledger[pref+'stdout'][0]and row['stderr']==ledger[pref+'stderr'][0]
  assert H(m[pref+'list.stdout'])==row['oracle'][0]and H(m[pref+'list.stderr'])==row['oracle'][1]
  assert ' 'in cmd['effective_sdk'] and sorted(r[-1]for r in phys['rustc'])==[0]*len(phys['rustc'])and all(r[-1]==0 for r in phys['wild'])
  bucket=Counter(r[0]for r in phys['rustc']);actual=[bucket['full'],bucket['link-only'],len(phys['wild']),row['fresh']]
  assert actual==[row['full'],row['link_only'],row['wild'],row['fresh']]
  expected=([636,0,201,0]if tag=='cold'else [1,50,50,563]if tag=='transitional'or k.endswith('B')else[0,0,0,619])
  assert actual==expected,(k,tag,actual)
  if actual[0]==1:assert row['rustc_full_names']==['ron']
  counts[k][tag]=actual
  rows=[json.loads(v)for v in m[pref+'stdout'].splitlines()];assert rows[-1]=={'reason':'build-finished','success':True}
  assert len([v for v in rows if v['reason']=='compiler-artifact'and v['fresh']])==row['fresh']
  if tag!='qual-2':continue
  assert row['products']=={physical:native['all_native_sha256'][k][n]for n,physical in native['physical_paths'][k].items()}
  assert native['states'][k]['receipt']==ledger[pref+'result.json'][0] and native['states'][k]['roster']==ledger[pref+'roster.json'][0]
  records[k]=row
  # Original-path digests are bound by the private ledger. Recompute typed correspondence after the named public registry alias.
  import namespace as ns
  target=Path(cmd['effective_sdk']).parent/'ruff-target';anchor,examples=ns.anchor(target,ro['units'])
  assert anchor==native['states'][k]['namespace'];norm,number=ns.canonical(target,ro['units'],anchor)
  assert number==native['states'][k]['normalized_typed_path_fields'];unitroots.add(H(canonical(norm)))
assert len(unitroots)==1 and len(counts)==4
exact={}
for l,r in combinations(native['states'],2):
 tag=l+'..'+r
 if tag not in native['comparisons']:l,r=r,l;tag=l+'..'+r
 chosen=native['comparisons'][tag];a,b=[native['all_native_sha256'][k]for k in(l,r)]
 differences={k for k in a if a[k]!=b[k]};assert set(chosen['different'])==differences and chosen['raw_equal']==110-len(differences)
 for n,z in chosen['different'].items():
  left,right=z['strict_normalization'];assert z['raw']==[a[n],b[n]]
  permitted=(left['bytes']==right['bytes'] and left['normalized']==right['normalized']and left['rodata_entsize']!=right['rodata_entsize']and min(left['rodata_entsize'],right['rodata_entsize'])==0 and left['build_id']!=right['build_id']);assert permitted==z['allowed']
  if not permitted:assert set(native['different_sections'][z['section_detail']])=={'.debug_info','.debug_macro','.debug_str','.note.gnu.build-id'}
 exact[tag]=[chosen['raw_equal'],chosen['allowed'],chosen['rejected']]
 assert exact[tag]==([105,1,4]if l[-1]!=r[-1]else[108,2,0]if l[-1]=='B'else [110,0,0])
assert len(fields['results'])==4 and all(fields['external_cli'][k]==fields['external_cli']['1-B']for k in counts)
for n,v in fields['results'].items():
 assert all([native['all_native_sha256'][r+'-B'][n],native['all_native_sha256'][r+'-C'][n]]==v['sha256']for r in'12')
 ch=v['differences'];assert ch['sizes'][0]==ch['sizes'][1]and set(ch['differing_bytes_by_section'])=={'.debug_info','.debug_macro','.debug_str','.note.gnu.build-id'}
 assert all(len(p)==1 and p[0][1]=='.debug_str'for p in ch['namespace_occurrences'])
 x,y=v['decoded'];assert x['debug_strings']==y['debug_strings']and x['debug_strings']['namespace_occurrences']==1
 for sec in ('macro','info'):
  assert all(x[sec][a]==y[sec][a]for a in('decoded','namespaces','str_offsets','lines'))and x[sec]['stderr_len']==y[sec]['stderr_len']==0 and x[sec]['lines']>10000
 assert v['same_under_literal_debug_audit']
if (root/'SHA256SUMS').exists():subprocess.run(['sha256sum','--quiet','-c','SHA256SUMS'],cwd=root,check=True)
print(json.dumps({'counts':counts,'native_comparisons':exact,'full_readelf_pairs':4,'clocks':0},sort_keys=True))
