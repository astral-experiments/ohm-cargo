"""Gate source/graph/current outputs and both directions before collecting any wall clocks."""
from pathlib import Path
import json,sys
def get(f):return json.loads(f.read_bytes())
def gate(root,sel):
 rows={};rawdiff=[];errors=[];counts={};expect={}
 def record(s,a,k):
  f=root/sel/s/a/k/'result.json';q=get(f);rows[(s,a,k)]=q;return q
 def check(x,stage,expected,actual=None):
  if not x:errors.append(dict(stage=stage,expected=expected,actual=actual))
 def oracle(q):
  return q['oracle']
 for st in ('original','older'):
  other='original' if st=='older'else'older'
  clean=record(st,'A-cold','cold');cc=record(st,'B-cold','cold');expect[st]=dict(clean=clean['products'],semantic=clean['semantic'],oracle=oracle(clean),targets=clean['targets'])
  ckeys=list(clean['semantic']);check(clean['semantic']==cc['semantic'],[st,'two independent clean products'],clean['semantic'],cc['semantic']);check(oracle(clean)==oracle(cc),[st,'two independent clean oracles'],oracle(clean),oracle(cc))
  for a in 'AB':
   for group,k,desired,first in ((a+'-trained','repeat',st,False),(a+'-probe','base',st,False),(a+'-probe','first',other,True),(a+'-probe','repeat',other,False),(a+'-probe','undo',st,True),(a+'-probe','undo-repeat',st,False)):
    v=record(st,group,k);anchor=record(desired,'A-cold','cold');label=[st,group,k]
    check(v['semantic']==anchor['semantic'],label+['complete selected inputs/outputs'],anchor['semantic'],v['semantic']);check(oracle(v)==oracle(anchor),label+['runtime / true diagnostic'],oracle(anchor),oracle(v));check(sorted(v['typed'],key=str)==sorted(anchor['typed'],key=str),label+['typed roster'],len(anchor['typed']),len(v['typed']))
    if v['products']!=anchor['products']:rawdiff.append(dict(row=label,expected=anchor['products'],actual=v['products']))
    if k=='first':
     required=2 if sel=='serde'else 1
     check(len(v['compile'])==required and all(w['package_root']for w in v['compile']),label+['actual root compilers'],required,[w['crate']for w in v['compile']])
     check(len(v['links'])==(1 if sel=='serde' else 0),label+['true Wild'],int(sel=='serde'),len(v['links']))
     check((v['marker_before']==v['marker_after'])==(a=='B'),label+['workspace resolution marker'],a=='B',v['marker_before']==v['marker_after'])
    if k in ('base','repeat','undo-repeat'):
     check(not v['compile'] and not v['links'] and all(v['fresh']),label+['true settled'],0,[len(v['compile']),len(v['links']),sum(v['fresh'])])
    counts['/'.join(label)]={'compilers':[w['crate']for w in v['compile']],'links':len(v['links']),'typed':len(v['typed']),'fresh':sum(v['fresh']),'root_flags':[w['lint']for w in v['compile']if w['package_root']],'marker_equal':v['marker_before']==v['marker_after']}
  ra=record(st,'A-trained','repeat');rb=record(st,'B-trained','repeat');check(ra['artifacts']==rb['artifacts'],[st,'trained entire typed output equality'],ra['artifacts'],rb['artifacts'])
 return dict(selection=sel,passed=not errors,errors=errors,raw_root_differences=rawdiff,phases=counts,clean=expect)
if __name__=='__main__':print(json.dumps(gate(Path(sys.argv[1]),sys.argv[2]),sort_keys=True))
