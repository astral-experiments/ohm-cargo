"""Read frozen v1 captures and real stock child exec/statuses without writing their source tree."""
import collections, gzip, hashlib, io, json, os, sys, tarfile
from pathlib import Path
P=Path('/mnt/devbox-scratch/dev-user/ohm-combined-prs-20261028')
R=P/'whole-wild-width-v1';sys.path.insert(0,str(R/'source'))
from wild import dep_names,digest,read,sha
from verify import body_info,process
from worker import K,W,PHASES,load,relative,role_kind
from view import six_phase_recipes
n=load(K/'ruff_worker.py')
def sig(b):return hashlib.sha256(b).hexdigest()
def hstr(s):return sig(s.encode())
def pack(v):return gzip.compress(json.dumps(v,sort_keys=True,separators=(',',':')).encode(),mtime=0)
def hdr(f):return {'name':f.name,'sha256':sha(f)}
def native_schema(receipt):
    # Reconstruct the precise Python pair type directly from original typed Cargo messages.
    expected=read(receipt/'products.json');msgs=[json.loads(l) for l in (receipt/'stdout').read_bytes().splitlines()]
    tuples=[(j['package_id'],j['message']) for j in msgs if j['reason']=='compiler-message']
    memory={**expected,'diagnostics':tuples}
    encoded=(json.dumps(memory,sort_keys=True,indent=2)+'\n').encode()
    assert encoded==(receipt/'products.json').read_bytes()
    return {'raw_json_sha256':sig(encoded),'bytes':len(encoded),'nonempty_pair_rows':len(tuples),
            'mismatching_keys_python':sorted(k for k in memory if memory[k]!=expected[k]),
            'schema_normalization_matches_all_physical_json_bytes':True}
def actual_seed():
    d=R/'commands/seed-repeat1';old=W/'seed-repeat1'
    new=read(d/'products.json');orig=read(old/'products.json')
    assert read(d/'command.json')['code']==0 and (R/'exit').read_text().strip()=='1' and not (R/'commands/seed-repeat2').exists()
    assert all(orig[k]==new[k] for k in ('fresh','units','counts','roster','ty_server','diagnostics','exes','e2e'))
    universe={**new['native'],**read(d/'registry-native.json')};assert universe==orig['native'] and len(universe)==186
    for path,h in universe.items():assert sha(n.actual(path,R/'states/seed'))==h
    key=read(R/'source/failed-native-fields.json')['fields']
    return {'phase':'seed-repeat1','status':0,'bytes_186_match_historical':True,'units':new['units'],'roster':new['roster'],
            'executables':len(new['exes']),'fresh':new['fresh'],'workspace_native':len(new['native']),'registry_native':len(universe)-len(new['native']),
            'raw_native_roster':{relative(k):v for k,v in universe.items()},'actual_counts':new['counts'],
            'diagnostics_count':len(new['diagnostics']),'diagnostics_sha256':digest(new['diagnostics']),
            'earlier_known_failure_sha256':{k:v['failed-unchanged']['sha256'] for k,v in key.items()}}
phasecheck={t:native_schema(W/t) for t in PHASES}
phasecheck['new-seed-repeat1']=native_schema(R/'commands/seed-repeat1')
assert phasecheck['new-seed-repeat1']['mismatching_keys_python']==['diagnostics']
summary=actual_seed()
assert not (R/'wall-view.json').exists()
opts=('failure-1','failure-2','seed-repeat1');files={};native={}
by_target=collections.defaultdict(list);anchors={};files_ledger={};children=0
for phase in opts:
 d=R/'commands'/phase;rows=n.trace_jobs(d/'trace');assert rows==read(d/'physical.json') and all(j['exit']==0 for j in rows)
 buf={int(j['pid'][5:]):j for j in rows if j['kind']=='wild'}
 cubes=list((R/'captures'/phase).iterdir());assert len(buf)==len(cubes)==(48 if phase=='seed-repeat1' else 1)
 physical={}
 for cube in cubes:
  c=read(cube/'capture.json');wild=buf[c['pid']];argv=read(cube/'raw-argv.json')
  assert argv==wild['argv'] and argv[argv.index('-o')+1]==c['target'] and digest(argv)==c['argv_sha256']
  stock={};core=process(d/'trace',c['default_pid'],argv);stock[str(c['default_pid'])]=core
  inp=read(cube/'positive-inputs.json');assert len(inp)==c['input_names'] and digest(inp)==c['inputs_sha256'] and sum(x['bytes'] for x in inp.values())==c['input_bytes']
  assert c['special_inputs']['symbols_sha256']==inp[c['special_inputs']['symbols']]['sha256']
  values={};prefix=c['target']
  for row in c['widths']:
   width=row['width'];dep=cube/(str(width)+'.d');plain=[*argv,'--threads='+str(width)];report=[*plain,'--dependency-file='+str(dep)]
   assert sha(dep)==row['dependency_receipt'] and dep_names(dep,Path(prefix))<=set(inp)
   assert digest(plain)==row['plain_argv_sha256'] and digest(report)==row['reported_argv_sha256']
   assert row['plain_exit']==row['depfile_exit']==0 and row['plain_sha256']==row['depfile_sha256']
   for pid,command in [(row['plain_pid'],plain),(row['depfile_pid'],report)]:stock[str(pid)]=process(d/'trace',pid,command)
   h=row['plain_sha256'];values[width]=h
   if h not in anchors:anchors[h]=body_info(R/'bodies'/h)
   assert anchors[h]['sha256']==h
  assert sorted(values)==list(range(1,17)) and c['raw_sha256'] in values.values() and len(stock)==33
  children+=len(stock)
  fields={h:anchors[h] for h in sorted(set(values.values()))}
  for role in ('observer','composed'):
   ss=W/('selected-'+role);saved=read(ss/'preserved-native.json')[prefix];pfile=ss/'native-files'/saved['file']
   for f in [pfile,n.actual(prefix,W/('state-'+role))]:
    v=body_info(f)
    assert all((w['normalized'],w['ranges'],w['bytes'])==(v['normalized'],v['ranges'],v['bytes']) for w in fields.values())
  if phase.startswith('failure-'):
   required=read(R/'source/failed-native-fields.json')['fields'][Path(prefix).name]['failed-unchanged']['sha256']
   assert c['raw_sha256']==required and required in values.values()
  expose_inputs=[[hstr(k),hstr(v['path']),v['bytes'],v['sha256']] for k,v in sorted(inp.items())]
  assert len(expose_inputs)==c['input_names']
  compact={'phase':phase,'target':relative(prefix),'role':role_kind(rows,prefix),'pid':c['pid'],'raw_exec':wild['raw'],
   'reported_and_plain_widths':c['widths'],'default_exit':c['default_exit'],'default_pid':c['default_pid'],'default_sha256':c['raw_sha256'],
   'actual_stock_trace_files':stock,'stock_image':c['wild_sha256'],'fully_resolved_inputs_sha256':c['inputs_sha256'],
   'all_hashes_of_literal_ordered_argv_entries':[hstr(v) for v in argv],'raw_argv_sha256':c['argv_sha256'],
   'all_positive_name_and_resolved_name_sha256_size_content':expose_inputs,'input_names':c['input_names'],'input_bytes':c['input_bytes'],
   'physical_positive_manifest':sha(cube/'positive-inputs.json'),'read_before_and_after':True,'physical_capture':sha(cube/'capture.json'),
   'elf_byte_ranges':fields,'original_pid_raw_exec':wild['raw']}
  by_target[Path(prefix).name].append(compact);physical[str(c['pid'])]=sha(cube/'capture.json')
 native[phase]={'physical':sha(d/'physical.json'),'captures':physical,'stock_children':33*len(cubes)}
 files_ledger[phase]={'capture_tree':digest(physical),'job_file':sha(d/'physical.json'),'targets':len(cubes)}
assert children==1650 and len(by_target)==48
copy_ledger={'protocol':sha(R/'source/SHA256SUMS'),'worker':sha(R/'source/worker.py'),'traceback':sha(R/'failure.txt'),
 'exit':sha(R/'exit'),'seed':sha(R/'seed.json'),'seed_617_products':sha(R/'commands/seed-repeat1/products.json'),
 'native_control_index':files_ledger,'original_registered_commit':read(R/'registration.json')['commit']}
files['stopped-source-binding.json']=(json.dumps(copy_ledger,indent=2,sort_keys=True)+'\n').encode()
for t,l in sorted(by_target.items()):files['links/'+t+'.json.gz']=pack(l)
files['phase-readback.json']=(json.dumps(phasecheck,indent=2,sort_keys=True)+'\n').encode()
files['comparison.json.gz']=pack(summary)
files['native-census.json']=json.dumps(native,sort_keys=True,indent=2).encode()+b'\n'
files['original-traceback.txt']=(R/'failure.txt').read_bytes()
files['verification.json']=(json.dumps({'native_first_phase_exit':0,'administrative_worker_exit':1,'cargo_phases_completed':1,'separate_failed_reconstructions':2,'stock_processes':children,'explicit':50*32,'default':50,'qualifying_combinations':50*16,'workspace_native_census':48,'diagnostic_python_pair_only':True,'no_clock_files_read':True},indent=2)+'\n').encode()
with tarfile.open(fileobj=sys.stdout.buffer,mode='w|') as tar:
 for k,data in sorted(files.items()):
  assert len(data)<8*1024**2
  i=tarfile.TarInfo(k);i.size=len(data);i.mtime=0;tar.addfile(i,io.BytesIO(data))
