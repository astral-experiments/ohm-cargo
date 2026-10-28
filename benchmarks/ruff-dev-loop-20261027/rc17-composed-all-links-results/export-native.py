"""Send only terminal, public-safe attestations, preserving exact private input identities."""
import gzip,hashlib,io,json,re,sys,tarfile
from pathlib import Path
R=Path('/mnt/devbox-scratch/dev-user/ohm-combined-prs-20261028/whole-wild-width-v1')
S=R/'source';P=R.parent
def rd(f):return json.loads(f.read_bytes())
def sha(p):
    with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def sig(s):return hashlib.sha256(s.encode()).hexdigest()
def digest(o):return hashlib.sha256(json.dumps(o,sort_keys=True,separators=(',',':')).encode()).hexdigest()
def z(o):return gzip.compress(json.dumps(o,separators=(',',':'),sort_keys=True).encode(),mtime=0)
PROTO=P/'whole-wild-width-v2-protocol'
BOOT=P/'whole-wild-width-v2-bootstrap'
assert (R/'exit').read_text().strip()=='1' and (PROTO/'exit').read_text().strip()=='1' and (BOOT/'exit').read_text().strip()=='0'
assert R.samefile(P/'whole-wild-width-v2')
continuation=rd(R/'continuation-registration.json')
preservation=rd(R/'physical-preservation.json')
assert preservation['preserved_sources_and_stop']
wall=rd(R/'wall-view.json');ind=rd(R/'independent.json')
assert ind['accepted'] and ind['all_untimed_stock_wild_processes']==9867 and len(wall['targets'])==50
files={}
def add(n,data):
 assert n not in files and len(data)<8*1024**2 and '..' not in n
 files[n]=data
for name in ['independent.json','terminal.json','registration.json','continuation-registration.json','tree-before-resume.json','physical-preservation.json','bootstrap-completion.json','reviewed-hashes.json','seed.json','qualification-source.json']:
 add(name,(R/name).read_bytes())
add('bootstrap-registration.json',(BOOT/'registration.json').read_bytes())
add('wall-view.json.gz',gzip.compress((R/'wall-view.json').read_bytes(),mtime=0))
add('wall-view.sha256',(sha(R/'wall-view.json')+'  wall-view.json\n').encode())
add('protocol.sha256',(sha(S/'SHA256SUMS')+'  SHA256SUMS\n').encode())
for name in ['failure-1','failure-2']:
 add('reconstructions/'+name+'.json',(R/'commands'/name/'gate.json').read_bytes())
phase_records={}
for phase in wall['fresh']:
 folder=R/'commands'/phase; prod=rd(folder/'products.json')
 workspace={str(Path(k).relative_to(P/'ruff-evaluation-v2/canonical')):v for k,v in prod['native'].items()}
 assert len(workspace)==len(prod['native'])==(108 if phase.startswith('seed') else 110)
 phase_records[phase]={'native':workspace,'units':prod['units'],'fresh':prod['fresh'],
   'exes':len(prod['exes']),'roster':prod['roster'],'counts':prod['counts'],'diagnostics':digest(prod['diagnostics']),
   'registry':sha(folder/'registry-native.json'),'e2e_listing':sha(folder/'e2e-list') if (folder/'e2e-list').is_file() else None,
   'trace_roster':sha(folder/'physical.json'),'status':rd(folder/'command.json')['code']}
add('commands.json.gz',z(phase_records))
for t,v in wall['targets'].items():
 basename=Path(t).name; data=rd(R/v['evidence']['file']);assert sha(R/v['evidence']['file'])==v['evidence']['sha256']
 rows={}
 for key,rec in data['recipes'].items():
  inp=rd(R/rec['raw_input_file']['file']);argv=rd(R/rec['raw_argv_file']['file'])
  assert digest(inp)==rec['inputs_sha256'] and digest(argv)==rec['stable_argv_sha256']
  capture=(R/rec['raw_input_file']['file']).parent
  raw=rd(capture/'capture.json')
  compact_inputs=[[sig(k),sig(f['path']),f['bytes'],f['sha256']] for k,f in sorted(inp.items())]
  traces={}
  trace=R/'commands'/rec['phase']/'trace'
  for pair in raw['widths']:
   ids=[pair['plain_pid'],pair['depfile_pid']]
   for pid in ids:traces[str(pid)]=sha(trace/('exec.'+str(pid)))
  pid=raw['default_pid'];traces[str(pid)]=sha(trace/('exec.'+str(pid)));assert len(traces)==33 and digest(traces)==rec['stock_trace_set_sha256']
  rows[key]={'phase':rec['phase'],'ordinal':rec['occurrence'],'raw_default':raw['raw_sha256'],'stock_processes':traces,
   'raw_argv_sha256':rec['stable_argv_sha256'],'all_ordered_argv_fields_sha256':[sig(a) for a in argv],
   'resolved_positive_and_literal_inputs_as_recorded':compact_inputs,'exact_physical_input_json_sha256':rec['raw_input_file']['sha256'],
   'public_input_projection_sha256':digest(compact_inputs),'kind': 'reconstructed' if rec['phase'].startswith('failure-') else 'workspace',
   'positive_names':raw['input_names'],'positive_bytes':raw['input_bytes'],'sizes_unchanged':True,
   'symbols_object_sha256':raw['special_inputs']['symbols_sha256'],'raw_dylibs_empty_directory':raw['special_inputs']['raw_dylibs_empty_directory'],
   'resolution_file_sha256':raw['special_inputs']['resolution_sha256'],'widths':raw['widths'],'whole_bodies':list(rec['bodies'])}
 add('links/'+basename+'.json.gz',z({'target':t,'recipes':rows,'exact_fields_and_unchanged_ranges':data['fields'],'raw_private_evidence':v['evidence']['sha256']}))
add('archive-source.json',json.dumps({'wall_view_sha256':sha(R/'wall-view.json'),'independent_sha256':sha(R/'independent.json'),
 'terminal_sha256':sha(R/'terminal.json'),'protocol_sha256':sha(S/'SHA256SUMS'),
 'origin':'charlie-ohm-c5-check-1025','original_logical_root':'whole-wild-width-v1','physical_results':'whole-wild-width-v2','immutable_initial_stop':'whole-wild-width-v1','public_export':'input/output/argument names individually SHA-256-bound; no native executables or private registry URLs included'},indent=2).encode()+b'\n')
with tarfile.open(mode='w|',fileobj=sys.stdout.buffer) as out:
 for name,data in sorted(files.items()):
  i=tarfile.TarInfo(name);i.size=len(data);i.mtime=0;out.addfile(i,io.BytesIO(data))
