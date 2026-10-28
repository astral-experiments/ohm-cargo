import csv,itertools,json,math,statistics
from collections import Counter
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
from common import *
def examine(which):
    d=HERE/which
    if not d.is_dir():return {'state':'pending'}
    if (d/'rejected.json').exists():return {'state':'rejected','problem':jread(d/'rejected.json'),'restored':(d/'restored.json').is_file() and jread(d/'restored.json')['matches_registration']}
    if not (d/'admission.json').is_file():return {'state':'pending admission'}
    if not (d/'samples.csv').is_file():return {'state':'admitted'}
    rows=list(csv.DictReader((d/'samples.csv').open()));samples={}
    for r in rows:samples.setdefault(int(r['pair_index']),[]).append(r)
    if len(rows)!=16 or not (d/'restored.json').is_file():return {'state':'collecting','rows':len(rows)}
    assert jread(d/'restored.json')['matches_registration']
    effects=[];deltas=[];byrole={'base':{},'candidate':{}};nonidentical=[];bycase=[]
    for i in range(8):
        pair=samples[i];assert len(pair)==2 and set(x['arm'] for x in pair)=={'base','candidate'} and pair[0]['source_sha256']==pair[1]['source_sha256']
        dv={r['arm']:int(r['total']) for r in pair};effects.append(1-dv['candidate']/dv['base'])
        deltas.append(math.log(int(pair[0]['total'])/int(pair[1]['total'])))
        bycase.append({'literal':int(pair[0]['literal_id']),'source_sha256':pair[0]['source_sha256'],'order':[r['arm'] for r in pair],'totals':dv,'saving':effects[-1]})
    for r in list(csv.DictReader((d/'admission.csv').open()))+rows:
        rec=jread(d/r['receipt'])
        for name,file in rec['files'].items():
            key=r['phase']+'-'+r['source_sha256']+'/'+name
            nonidentical.append((key,r['arm']+'/'+r['mode'],file['sha256'],file['canonical_sha256']))
    hashes={}
    for k,arm,full,norm in nonidentical:
        o=hashes.setdefault(k,{'full_sha256s':{},'canonical_sha256s':[]})
        o['full_sha256s'][arm]=full
        if norm not in o['canonical_sha256s']:o['canonical_sha256s'].append(norm)
    for k,o in hashes.items():assert len(o['canonical_sha256s'])==1
    save(d/'artifact-digests.json',hashes)
    for arm,tot in byrole.items():
        arr=[r for r in rows if r['arm']==arm]
        for role in ['cargo','rustc','wild','total']:tot[role]=statistics.median(int(r[role]) for r in arr)
    wins=sum(x>0 for x in effects);loss=sum(x<0 for x in effects);n=wins+loss
    sign=min(1,2*sum(math.comb(n,k) for k in range(min(wins,loss)+1))/2**n) if n else 1
    observed=abs(sum(d if samples[i][0]['arm']=='base' else -d for i,d in enumerate(deltas)))
    perm=sum(abs(sum(d if i in comb else -d for i,d in enumerate(deltas)))>=observed-1e-12 for comb in itertools.combinations(range(8),4))/70
    med=statistics.median(effects);passed=med>0 and sign<.05 and perm<.05
    result={'state':'qualified' if passed else 'inconclusive','n_pairs':8,'counted_commands':16,'counted_role_processes':192,'additional_admission_commands':4,'num_distinct_emitted':72,'mean_by_arm':{a:sum(int(r['total']) for r in rows if r['arm']==a)/8 for a in byrole},'median_instructions_by_role':byrole,'median_saving':med,'rank_interval_99_21875':[min(effects),max(effects)],'wins':wins,'losses':loss,'ties':8-n,'two_sided_sign_p':sign,'balanced_order_randomization_p':perm,'raw_pair_summaries':bycase,'full_digest_variant_combinations':{k:v for k,v in hashes.items() if len(set(v['full_sha256s'].values()))>1},'restored':True}
    save(d/'summary.json',result);return result
def summarize():
    states={w:examine(w) for w in ('initial','replica')}
    summary={'qualified':all(s['state']=='qualified' for s in states.values()),'cohorts':states}
    save(HERE/'summary.json',summary)
    return summary
if __name__=='__main__':print(json.dumps(summarize(),indent=2))
