from pathlib import Path
import collections,gzip,hashlib,json,re,sys
def sha(p):
 with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def examine(d):
 h={f:sha(d/f) for f in ('cargo.stderr','cargo.stdout','native-jobs.json.gz','complete.json')}
 r=json.loads((d/'complete.json').read_bytes())
 assert r['cargo']['stdout']==h['cargo.stdout'] and r['cargo']['stderr']==h['cargo.stderr'] and r['native']['native_jobs']==h['native-jobs.json.gz']
 jobs=json.load(gzip.open(d/'native-jobs.json.gz'))
 fingerprint=collections.defaultdict(list)
 raw=(d/'cargo.stderr').read_text().splitlines()
 pref='cargo::compiler::fingerprint: '
 log=[l.split(pref,1)[1] for l in raw if pref in l]
 for i,m in enumerate(log):
  if not m.startswith('fingerprint dirty for '):continue
  nxt=log[i+1].strip()
  assert nxt.startswith('dirty: '),(m,nxt)
  a=re.match(r'^fingerprint dirty for ([^ ]+) v[^ ]+?(?: \(.+?\))?/(Build|RunCustomBuild|Test)/TargetInner ',m)
  assert a,m
  pkg,mode=a.groups()
  src=re.findall(r'"([^"]+\.rs)"',m)
  assert len(src)==1,m
  u=re.fullmatch(r'dirty: FsStatusOutdated\(StaleDepFingerprint \{ unit: UnitIndex\((\d+)\) \}\)',nxt)
  path=re.fullmatch(r'dirty: FsStatusOutdated\(StaleItem\((MissingFile|MissingChecksum) \{ path: "([^"]+)" \}\)\)',nxt)
  if u:reason='dependency-fingerprint';detail='unit-'+u[1]
  else:
   assert path,(m,nxt)
   reason=path[1];detail=Path(path[2]).name
   if '/dev/null/' not in path[2]:assert detail=='ohm-foreign-span-bytes',nxt
  fingerprint[pkg,mode,src[0]].append((reason,detail,hashlib.sha256(m.encode()).hexdigest(),hashlib.sha256(nxt.encode()).hexdigest()))
 rows=[json.loads(b) for b in (d/'cargo.stdout').read_bytes().splitlines()]
 arts=[a for a in rows if a['reason']=='compiler-artifact']
 assert len(arts)==r['units']
 answer=[]
 for j in jobs:
  if j['kind'] not in ('rustc-full','rustc-cached') or '--crate-name' not in j['args']:continue
  av=j['args'];p=Path(av[av.index('--out-dir')+1]);pkg=p.parent.parent.name;unit=p.parent.name
  rootarg=[s for s in av if s.endswith('.rs') and not s.startswith('-')]
  assert len(rootarg)==1,(pkg,rootarg);name=j['crate'];test='--test' in av
  matches=[]
  for a in arts:
   x=a['target']
   if x['name'].replace('-','_')!=name or not x['src_path'].endswith(rootarg[0]):continue
   if a['fresh']:continue
   actualname=[Path(s) for s in a['filenames']]
   if any(unit in s.name or unit in s.parts for s in actualname) or x['kind']==['custom-build'] or (x['kind'] in (['bin'],['example']) and not test and not a['profile']['test'] and a['executable'] and Path(a['executable']).name==x['name'] and actualname==[Path(a['executable'])]):matches.append(a)
  assert len(matches)==1,(pkg,name,unit,type(test),rootarg,len(matches),[(a['target']['name'],a['filenames']) for a in arts if a['target']['name'].replace('-','_')==name and not a['fresh']][:4])
  a=matches[0];cargo_test=bool(a['profile']['test']);k=(pkg,'Test' if cargo_test else 'Build',a['target']['src_path']);c=fingerprint[k]
  # Cargo's text omits the unit hash. Every observed candidate needs to agree on the immediate cause.
  assert c,(k,name,unit)
  cls=sorted(set(t[:2] for t in c));cat=a['target']['kind']
  answer.append(dict(package=pkg,crate=name,unit=unit,compiler_test=test,cargo_profile_test=cargo_test,kind=cat,actual_argv=j['argv_sha256'],reason_classes=sorted({q[0] for q in cls}),details=sorted({q[1] for q in cls}),matching_rows=len(c),raw_log_line_pairs=sorted(set(t[2:] for t in c))))
 assert len(answer)==len(r['actual_rosters']['rustc']) and len({v['unit'] for v in answer})==len(answer)
 return {'scope':'Ordinary W/7277 same-source diagnostic with CARGO_LOG=cargo::compiler::fingerprint=info; join physical --out-dir, source and test mode to Cargo typed target and logged prepare_target. Duplicate feature-unit logs retain every matching reason.','raw':h,'comparable':r['comparable'],'active_units':len(arts),'cargo_dirty_typed':sum(not a['fresh'] for a in arts),'dirty_lines':sum(map(len,fingerprint.values())),'native':r['native']['counts'],'actual_full':answer,'reason_by_full':{}}
if __name__=='__main__':
 out=examine(Path(sys.argv[1]));out['reason_by_full']=dict(collections.Counter('/'.join(v['reason_classes']+[s for s in v['details'] if not s.startswith('unit-')])for v in out['actual_full']))
 print(json.dumps(out,indent=2,sort_keys=True))
