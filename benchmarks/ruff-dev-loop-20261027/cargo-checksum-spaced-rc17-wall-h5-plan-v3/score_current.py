"""Run the original H5 schedule against four immutable, fully decoded cross-compiler debug pairs."""
from pathlib import Path
import argparse,collections,contextlib,fcntl,hashlib,itertools,json,os,re,subprocess,sys,time,traceback
here=Path(__file__).resolve().parent;q=here.parent;proto=q/'protocol-v2';sys.path.insert(0,str(proto))
import worker as w
import namespace as ns
base=q/'qualified-wall-study-v3';data=base/'wall'
def admission():
 g=w.read(here/'amendment.json');pub=w.read(here/'publication.json')
 assert set(pub)=={'plan_commit','native_commit','manifest'}and re.fullmatch('[0-9a-f]{40}',pub['plan_commit'])and re.fullmatch('[0-9a-f]{40}',pub['native_commit'])
 assert pub['manifest']==w.sha(here/'SHA256SUMS')and w.sha(here/'plan.json')==w.sha(proto/'plan.json')==g['original_plan_sha']
 assert (q/'launch-train/exit').read_text()==(q/'launch-audit/exit').read_text()=='1' and not(q/'wall').exists()and not(q/'qualified.json').exists()
 assert w.sha(q/'diagnostic-private/structural.json')==g['strict_native'] and w.sha(q/'diagnostic-private/dwarf-debug.json')==g['actual_debug_raw']
 ev=w.read(q/'diagnostic-private/structural.json');debug=w.read(q/'diagnostic-private/dwarf-debug.json')
 allowed=w.read(here/'checked-pairs.json')
 assert len(allowed)==4 and all(y['same_under_literal_debug_audit'] for y in debug['results'].values())
 assert {n:y['sha256']for n,y in debug['results'].items()}==allowed
 assert w.plan['orders']==g['orders']and w.plan['clock']==g['clock']and all(g['frozen_helpers'][n]==w.sha(proto/n)==w.sha(here/n)for n in ('clock.py','elf.py','statistics_replication.py'))
 refs={};positions={};maps={};rosters=set();diffs=set()
 for k,x in ev['states'].items():
  b=int(k[0]);a=k[2];st=w.alias_state(b,a)/'target';p=w.regpath(b,a);r=w.read(p)
  assert x['receipt']==w.sha(p)==g['arm_receipts'][k]
  assert w.products(b,a,r['guards']['native_paths'])==r['products']
  raw=w.read(p.parent/'roster.json');bound=w.read(here/'anchors.json')[a]['namespace']
  norms,replacements=ns.canonical(w.logical_target,raw['units'],bound); assert bound==x['namespace']and ns.digest(norms)==x['normalized_units']and replacements==x['normalized_typed_path_fields'];rosters.add(ns.digest(norms));diffs.add(ns.digest(raw['diagnostics']))
  nmap=ev['physical_paths'][k]
  assert ev['all_native_sha256'][k]=={n:r['products'][t]for n,t in nmap.items()}and set(r['products'])==set(nmap.values())
  assert len(nmap)==110 and all(r['products'][nmap[n]]==v['BC'.index(a)]for n,v in allowed.items())
  assert r['guards']['units']==619 and r['guards']['harness_profile']==84 and r['guards']['nonharness_profile']==18
  assert [r['full'],r['link_only'],r['wild'],r['fresh']]==([1,50,50,563] if a=='B'else[0,0,0,619])
  refs[k]=r;positions[k]={n:w.elf.normalize(st/n)for n in r['products']};maps[k]=nmap
 assert len(rosters)==len(diffs)==1
 # Apply the original all-byte rule to every other cross-arm/cross-training mismatch,
 # and exempt only the exact matched pair with its exact native canonical filename.
 for l,rr in itertools.combinations(refs,2):
  for canon,n in maps[l].items():
   other=maps[rr][canon];sig=refs[l]['products'][n];sig2=refs[rr]['products'][other]
   if sig==sig2:continue
   if canon in allowed and l[-1]!=rr[-1]:
    assert (sig,sig2)==tuple(allowed[canon]['BC'.index(state[-1])]for state in(l,rr));continue
   left=positions[l][n];right=positions[rr][other];assert left['normalized']==right['normalized']and left['bytes']==right['bytes'] and left['rodata_entsize']!=right['rodata_entsize'] and min(left['rodata_entsize'],right['rodata_entsize'])==0 and left['build_id']!=right['build_id']
 return refs,positions,maps,allowed
def verify_native(b,a,now,refs,positions,maps,allowed):
 k=w.state_label(b,a);old=refs[k]['products'];assert set(now)==set(old)
 if a=='C':assert now==old
 assert all(now[maps[k][n]]==v['BC'.index(a)]for n,v in allowed.items())
 return w.check_native(b,a,now,old,positions[k])
def slot(b,a,j,refs,positions,maps,allowed):
 k=w.state_label(b,a);dest=data/('block-'+str(b))/f'{j:02}-{a}';dest.mkdir(parents=True)
 w.run(w.ns(b,a,dest)+['/usr/bin/python3','-B',str(proto/'clock.py'),str(dest),*w.command],dest/'outer.stdout',dest/'outer.stderr',w.environment())
 assert (dest/'outer.stdout').stat().st_size==(dest/'outer.stderr').stat().st_size==(dest/'stdout').stat().st_size==0
 stderr=(dest/'stderr').read_bytes();assert b'Finished'in stderr and b'Blocking waiting'not in stderr
 n=len(re.findall(rb'^\s*Compiling\s+',stderr,re.M));assert (a=='B'and n>0)or(a=='C'and n==0)
 clock=w.read(dest/'clock.json');assert clock['returncode']==0 and clock['elapsed_ns']==clock['stop']-clock['start']>0 and clock['argv']==w.command
 r=refs[k];now=w.products(b,a,r['guards']['native_paths']);qual=verify_native(b,a,now,refs,positions,maps,allowed)
 harness=w.oracle(b,a,dest,r['guards']['harness']);assert harness==r['oracle']
 w.put(dest/'verified.json',{'ns':clock['elapsed_ns'],'stdout':w.sha(dest/'stdout'),'stderr':w.sha(dest/'stderr'),'stdout_bytes':0,'compiler_progress_lines':n,'products':now,'variation':qual,'harness':harness})
 return clock['elapsed_ns']
def main():
 assert not base.exists()and sorted(os.sched_getaffinity(0))==list(range(8))and not(q/'wall').exists()and not(q/'launch-score').exists()
 assert os.uname().nodename=='charlie-ohm-loader-perf-1024';subprocess.run(['sha256sum','--quiet','-c','SHA256SUMS'],cwd=here,check=True)
 w.clean();w.guard()
 with(w.p/'native-measure.lock').open('rb')as lock:
  fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB);refs,positions,maps,allowed=admission()
  base.mkdir(mode=0o700);allrows=[]
  for b,orders in enumerate(w.plan['orders'],1):
   pairs=[]
   for j,order in enumerate(orders,1):
    obs={a:slot(b,a,j,refs,positions,maps,allowed)for a in order};pairs.append({'order':order,'ns':obs});w.put(data/f'ledger-{b}.json',pairs)
   allrows.append(pairs)
  for b,a in [(1,'B'),(1,'C'),(2,'B'),(2,'C')]:
   post=w.observe(b,a,'post-clock-h5-v3');ref=refs[w.state_label(b,a)]
   assert post['dirty']==ref['dirty']and post['guards']==ref['guards']and post['oracle']==ref['oracle']and post['rustc_full_names']==ref['rustc_full_names']
   assert [post[n]for n in('full','link_only','wild','fresh')]==[ref[n]for n in('full','link_only','wild','fresh')]
   verify_native(b,a,post['products'],refs,positions,maps,allowed)
  w.clean();w.guard()
  w.put(data/'all.json',allrows);w.put(data/'result.json',w.analyze(allrows,w.plan));w.put(data/'complete.json',{'manifest':w.sha(here/'SHA256SUMS'),'release':w.read(here/'publication.json'),'pairs':w.sha(data/'all.json'),'wall_commands':24,'post_clock_native_controls':4})
if __name__=='__main__':
 try:main()
 except BaseException:
  (q/('failed-score-v3-'+str(time.time_ns())+'.txt')).write_text(traceback.format_exc());raise
