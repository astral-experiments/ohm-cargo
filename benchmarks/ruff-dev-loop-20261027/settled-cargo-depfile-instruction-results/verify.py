"""Recompute every process count, paired result, native artifact roster and focused control."""
import gzip, hashlib, importlib.util, json, sys
from pathlib import Path
B=Path(__file__).resolve().parent
h=lambda b:hashlib.sha256(b).hexdigest()
j=lambda p:json.loads(p.read_bytes())
gz=lambda p:gzip.decompress(p.read_bytes())
serialized=lambda obj:(json.dumps(obj,indent=2,sort_keys=True)+'\n').encode()
P=j(B/'plan.json'); assert h((B/'plan.json').read_bytes())=='837b7729e5b41c1348453a641ede1528d8023988adfc318b6081b869a17f5fcb'

def verify_files(directory):
 p=directory/'SHA256SUMS'
 if p.is_file():
  for line in p.read_text().splitlines():
   digest,filename=line.split('  ',1);assert not Path(filename).is_absolute() and '..' not in Path(filename).parts and h((directory/filename).read_bytes())==digest,filename

def check_mode(host,name,arg,units,products,depfiles):
 m=B/host/name;n=m/'native';native=j(m/'original-and-portable.json');rows=j(m/'observations.json');original=[]
 for fn,digest in native.items():assert h(gz(n/(fn+'.gz')))==digest['portable_sha256'],fn
 anchor=json.loads(gz(n/'anchor.json.gz'));assert anchor==json.loads(gz(n/'parent.json.gz'))==json.loads(gz(n/'candidate.json.gz'));assert units==anchor['units'] and products==len(anchor['products'])==len(anchor['product_stamps']) and depfiles==len(anchor['dot_d'])
 assert anchor['proofs']['.ohm-git-index-sha1dc-v1'][0]>0 and anchor['proofs']['.ohm-registry-json-v2'][0]>0
 stages=['trace-parent','trace-candidate','post-ir','post-wall']+(['isolation-parent','isolation-candidate'] if host=='h8' else [])
 for key in stages:
  p=n/key;row=json.loads(gz(p/'record.json.gz'));assert row['units']==units and len(row['physical'])==2 and all(Path(f).name=='cargo' for f in row['physical']);assert set(row['products'])==set(anchor['products'])
  outputs=[v for b in gz(p/'stdout.gz').splitlines() if (v:=json.loads(b)).get('reason')=='compiler-artifact'];assert len(outputs)==units and all(v['fresh'] for v in outputs) and {str(f) for v in outputs for f in v['filenames']}==set(anchor['products'])
  assert row['stdout']==native[key+'/stdout']['raw_sha256'] and row['stderr']==native[key+'/stderr']['raw_sha256']
  logs=list(p.glob('exec.*.gz'))
  if logs:
   physical=[l.split('execve("',1)[1].split('"',1)[0] for f in sorted(logs) for l in gz(f).decode().splitlines() if 'execve("' in l and l.endswith('= 0')];assert sorted(physical)==sorted(row['physical']),key
 for r in rows:
  kind=r['metric'];pos=r['position'];pair=r['pair'];arm=r['arm'];assert arm==P['orders'][name][kind][pair][pos] and r['rc']==0 and r['stdout']==h(b'') and r['maxrss_kib']>0
  dest=m/kind/f'{pair:02}-{pos}-{arm}'/'stderr.gz';assert h(gz(dest))==r['stderr_fixture']['portable_sha256'] and r['stderr']==r['stderr_fixture']['raw_sha256'] and b'Finished' in gz(dest)
  orig=dict(r)
  for k in ['mode','metric','pair','position','arm','source_record_sha256','stderr_fixture']:orig.pop(k)
  if kind=='ir':
   raw=r['raw_report'].encode();a=r['argv'];lines=[l.split() for l in r['raw_report'].splitlines()];ts=[l[2] for l in lines if l[0]=='T'];es={l[2]:int(l[3]) for l in lines if l[0]=='F'};pid={l[1] for l in lines if l[0] in ('B','P','T','F')};assert len(pid)==1 and len(ts)==len(es)==len(set(ts)) and lines[0][0]=='B' and lines[-1][0]=='P' and es==r['threads'] and set(ts)==set(es) and sum(es.values())==r['ir'];assert h(raw)==r['count_sha256'] and h(b'\0'.join(x.encode() for x in a)+b'\0')==r['actual_argv_sha256'] and a[1:]==arg
   orig.pop('actual_argv_sha256');orig.pop('raw_report')
  else:assert kind=='wall' and r['elapsed_ns']>0
  assert h(serialized(orig))==r['source_record_sha256'];original.append((kind,pair,pos))
 assert len(set(original))==len(original)==96 and {r['pair'] for r in rows if r['metric']=='ir'}==set(range(16)) and {r['pair'] for r in rows if r['metric']=='wall'}==set(range(32))

def verify_support():
 d=B/'support';verify_files(d)
 for n,dig in j(d/'original-and-portable.json').items():
  p=d/n;assert h(gz(p) if str(p).endswith('.gz') else p.read_bytes())==dig['portable'],n
 tests=j(d/'cargo-tests/results.json');full=j(d/'cargo-tests/full-cargo-unit-tests.json');assert full['rc']==0 and '406 passed; 0 failed' in full['summary'][0];assert len(tests)==3 and all(x['rc']==0 for x in tests.values())
 for n in ('package-controls-v3','output-wire-control','observer-dot-d-control'):
  p=j(d/'functional'/n/'complete.json');assert p['parent']==p['candidate']
 v=j(d/'functional/observer-dot-d-control/complete.json')['parent'];assert [v[k]['complete'] for k in ['first','train','settled','corrupt','retrain','recovered']]==[0,1,1,0,1,1];assert v['recovered']['fresh'] and all(v[k]['marker']!=bool(v[k]['complete']) for k in v)
 v=j(d/'functional/output-wire-control/complete.json')['parent'];assert v['raw-invalid']['rc']==101 and v['alias']['rc']==0
 v=j(d/'functional/package-controls-v3/complete.json')['parent'];assert v['nonutf_rc']==101 and v['before']==17 and v['after']==29
 for r in sorted((d/'profile/scoped-block/rows').iterdir()):
  report=j(r/'verified.json');raw,=r.glob('profile-*');assert h(raw.read_bytes())==report['raw'];assert sum(int(v) for v in report['bins'].values())==report['groups']['all'];assert 29_000_000<report['groups']['output-graph']<30_000_000
 p=d/'profile/output-path-study';v=j(p/'replay.json');assert v['input']==h(gz(p/'input.gz')) and v['gold']==h(gz(p/'output.gz'))
 for r in v['rows']:
  f=p/('count-'+r['mode']);assert h(f.read_bytes())==r['raw'] and r['ir']==sum(int(l.split()[3]) for l in f.read_text().splitlines() if l.startswith('F '))

def main():
 verify_files(B);verify_support();pairfile=B/'pilot-receipts/qualified-pair.json';pair=j(pairfile);assert h(pairfile.read_bytes())==P['matched_pair']
 for arm in ('parent','candidate'):
  x=pair[arm];assert x['sha256']==P['subjects'][arm] and x['common_inputs']==P['common_nonproduct_dependency_inputs'] and x['profile']==P['compiler_build_profile'] and x['source_baseline']=='a0c7d08c898d3fdff992f2f431dec57d2486add2'
 assert pair['parent']['version']==pair['candidate']['version'] and pair['parent']['compiler']==pair['candidate']['compiler'];assert h((B/'implementation/product.patch').read_bytes())==j(B/'implementation/source.json')['patch']
 helper=importlib.util.spec_from_file_location('paired',B/'implementation/analyze.py');module=importlib.util.module_from_spec(helper);helper.loader.exec_module(module)
 for m,n,p,d in [('library',268,492,1),('workspace',501,922,58),('test',619,1060,15)]:
  host=P['endpoints'][m][0];verify_files(B/host);args={'library':['build','--lib'],'workspace':['build'],'test':['test','--no-run']}[m]+['--locked','--offline','-j4'];check_mode(host,m,args,n,p,d)
 answer=module.main(B);assert answer==j(B/'results.json');print('288 native process results, including 96 thread-complete instruction counts; all .d and artifact gates passed.');print(json.dumps(answer,sort_keys=True,indent=2))
if __name__=='__main__':main()
