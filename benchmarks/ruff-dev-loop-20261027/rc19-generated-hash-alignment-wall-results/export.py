"""Read-only result export. Recompute every time and gate, retain a failed prefix without inference."""
from pathlib import Path
import hashlib,json,os,re
D=Path.home()/'.cache/ohm-script-hash-wall-rc19-v1';s=D/'score';hostname=os.uname().nodename;role='primary-linux'if'loader-'in hostname else'independent-linux';hashfile=lambda p:hashlib.sha256(p.read_bytes()).hexdigest();digest=lambda x:hashlib.sha256(json.dumps(x,sort_keys=True,separators=(',',':')).encode()).hexdigest();rd=lambda p:json.loads(p.read_bytes());pre=rd(D/'release-native-final/pre.json');g=rd(D/'grant-final.json');plan=rd(D/'plan.json');obs=[];ls=s/'slots.jsonl';rawrows=[json.loads(l)for l in ls.read_text().splitlines()]if ls.is_file()else[]
fail=sorted((D/'release-native-final').glob('failed-score-*.txt'));terminal=s/'terminal.json';assert terminal.exists() or fail
for p in sorted(s.glob('*-*-?'))if s.is_dir()else[]:
 i,j,arm=p.name.split('-');i=int(i);j=int(j);assert arm==plan['domains'][hostname]['strata'][i][j]
 if not(p/'clock.json').is_file():assert fail;break
 cr=rd(p/'clock.json');stdout=(p/'stdout').read_bytes();stderr=(p/'stderr').read_bytes();assert (cr['stratum'],cr['position'],cr['arm'])==(i,j,arm)and cr['elapsed_ns']==cr['end']-cr['start']>0 and cr['stdout']==hashfile(p/'stdout')and cr['stderr']==hashfile(p/'stderr')and cr==rawrows[len(obs)]
 txt=stderr.decode();checks='Finished 'in txt and 'Compiling 'not in txt and 'error:'not in txt;assert checks==cr['fresh_text']
 if terminal.is_file():assert stdout==b''and cr['rc']==0 and checks and re.fullmatch(r'\s*Finished `dev` profile \[optimized \+ debuginfo\] target\(s\) in [0-9.]+s\s*',txt),txt
 obs.append({**cr,'complete_stdout':stdout.decode(),'complete_stderr':txt,'raw_clock_sha256':hashfile(p/'clock.json')})
assert len(obs)==len(rawrows)
result={'role':role,'native_before':hashfile(D/'release-native-final/pre.json'),'native_release_ref':g['native_release_ref'],'source':hashfile(D/'wall-final.py'),'images':g['images'],'source_plan':g['source_plan'],'rows':obs,'terminal':terminal.is_file(),'private_grant_sha256':hashfile(D/'grant-final.json'),'source_plan_sha256':hashfile(D/'plan.json'),'raw_ledger_sha256':hashfile(ls)if ls.exists()else None}
if terminal.is_file():
 t=rd(terminal);post=D/'release-native-final/post.json';pr=rd(post);assert len(obs)==384 and len(rawrows)==len(t['rows'])and t['rows']==rawrows and t['terminal']and hashfile(post)==t['post_guards']and result['native_before']==t['pre_guards'];assert pre['source']==pr['source']==result['source']
 for a in 'AB':
  aa=pre['arms'][a];bb=pr['arms'][a];assert all(aa[k]==bb[k]for k in ('files','semantics','cargo','state_inode','cargo_inode','cache_hits','metadata'))
 result.update(begin_load=t['begin_load'],end_load=t['end_load'],post_guards=hashfile(post),pre_guards=t['pre_guards'],per_arm_complete_post={a:{'raw_complete_map':digest(pr['arms'][a]['files']),'file_count':len(pr['arms'][a]['files']),'actual_native_evidence_sha256':pr['arms'][a]['full_native'],'semantic_fields':pr['arms'][a]['semantics']}for a in 'AB'},raw_terminal_sha256=hashfile(terminal))
else:result['first_failure_sha256']=hashfile(fail[0]);result['timing_estimate']=None
print(json.dumps(result,sort_keys=True))
