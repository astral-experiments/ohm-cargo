"""Check the full portable 50-occurrence, 1,650-stock-child partial native result."""
from pathlib import Path
import collections,gzip,hashlib,json,re
D=Path(__file__).resolve().parent
def rd(f):return json.loads(gzip.decompress(f.read_bytes()) if f.suffix=='.gz' else f.read_bytes())
def verify():
 summary=rd(D/'verification.json');assert summary['native_first_phase_exit']==0 and summary['administrative_worker_exit']==1
 cnt=collections.Counter();n=0;raw=0;example={};files=list((D/'links').glob('*.json.gz'));assert len(files)==48
 for f in files:
  rows=rd(f)
  for row in rows:
   phase=row['phase'];cnt[phase]+=1
   assert row['stock_image']=='0d6335808b647d499f3d74993b602e64ff0625206c809bf4913c487eea380cd5'
   pairs=row['reported_and_plain_widths'];assert sorted(w['width'] for w in pairs)==list(range(1,17)) and len(pairs)==16
   inp=row['all_positive_name_and_resolved_name_sha256_size_content'];assert len(inp)==row['input_names'] and sum(i[2] for i in inp)==row['input_bytes'] and all(len(i[0])==len(i[1])==len(i[3])==64 for i in inp)
   proc=row['actual_stock_trace_files'];assert len(proc)==33 and str(row['default_pid']) in proc and row['default_exit']==0
   for w in pairs:
    assert w['plain_exit']==w['depfile_exit']==0 and w['plain_sha256']==w['depfile_sha256'] and str(w['plain_pid']) in proc and str(w['depfile_pid']) in proc
   hashes={w['plain_sha256'] for w in pairs};assert row['default_sha256'] in hashes and set(row['elf_byte_ranges'])==hashes
   assert len({(x['normalized'],x['bytes'],json.dumps(x['ranges'])) for x in row['elf_byte_ranges'].values()})==1
   if phase.startswith('failure-'):
    expect={w['width'] for w in pairs if w['plain_sha256']==row['default_sha256']}
    assert expect==set(range(2,17));example[Path(row['target']).name]=row['default_sha256']
   n+=len(proc);raw+=len(hashes)
 assert cnt=={'failure-1':1,'failure-2':1,'seed-repeat1':48} and n==1650 and len(example)==2
 matches=rd(D/'comparison.json.gz');assert matches['earlier_known_failure_sha256']==example
 assert len(matches['raw_native_roster'])==186 and matches['workspace_native']==108 and matches['registry_native']==78
 assert matches['actual_counts']=={'full':1,'link-only':48,'wild':48} and matches['units']==617 and matches['fresh']==563
 phases=rd(D/'phase-readback.json');assert len(phases)==7 and all(v['schema_normalization_matches_all_physical_json_bytes'] for v in phases.values())
 assert phases['new-seed-repeat1']['mismatching_keys_python']==['diagnostics'] and phases['new-seed-repeat1']['nonempty_pair_rows']==1
 bind=rd(D/'stopped-source-binding.json');assert hashlib.sha256((D/'original-traceback.txt').read_bytes()).hexdigest()==bind['traceback']
 return {'stock_links_attested':n,'true_native_occurrences':sum(cnt.values()),'complete_width_pairs':800,'raw_counts_per_occurrence_sum':raw,'historical_command_readbacks':len(phases)-1,
         'genuine_workspace_raw_equal':108,'genuine_registry_raw_equal':78,'two_default_failures_reproduced':example,'worker_exit':1,'cargo_exit':0}
if __name__=='__main__':print(json.dumps(verify(),sort_keys=True,indent=2))
