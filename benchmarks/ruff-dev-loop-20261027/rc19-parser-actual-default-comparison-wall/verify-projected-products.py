from collections import Counter
from pathlib import Path
import csv
import hashlib
import json

p=Path(__file__).resolve().parent
def load(f):return json.loads(f.read_bytes())
def digest(f):return hashlib.sha256(f.read_bytes()).hexdigest()
def main():
    for line in (p/'SHA256SUMS').read_text().splitlines():
        h,n=line.split('  ',1)
        assert digest(p/n)==h,n
    refs=load(p/'native-product-references.json')
    bound=load(p/'raw-bindings.json')
    assert refs['native_packet']==bound['portable_native']
    original=load(p/'stock-wild-variants.json')
    plan=load(p/'plan.json')
    seen=Counter()
    arm_sizes={role:set() for role in 'RF'}
    clocks=list(csv.DictReader((p/'clocks.csv').read_text().splitlines()))
    assert len(clocks)==24
    idx=0
    for pair,order in enumerate(plan['orders'],1):
        for stage,state in [('edit','P'),('reset','H')]:
            for pos,role in enumerate(order if stage=='edit' else order[::-1],1):
                label=f'{pair:02d}-{stage}/{role}'
                root=p/'wall'/label
                pk=load(root/'post.json')
                assert pk['typed_fresh']==147 and pk['cargo_rc']==0
                rv=bound['outputs'][label];assert rv['euid']==1000 and rv['full_uid_map']==['0','0','4294967295'] and rv['cpu']==[24,25,26,27]
                for name,info in pk['products'].items():
                    subj=refs[state][name]
                    assert all(info[k]==subj[k] for k in ('test','list_sha','listed','width_neutral'))
                    if subj['sha']==info['sha']:
                        seen['raw_equal_to_native_record']+=1
                    else:
                        assert name=='fixtures' and info['sha']==original[state]['variants']['0']['elf_sha256']
                        seen['raw_equal_to_full_stock_wild_reconstruction']+=1
                    if name=='fixtures':
                        arm_sizes[role].add(next(k for k,x in original[state]['variants'].items() if x['elf_sha256']==info['sha']))
                seen['post_all_147_fresh']+=1
                if stage=='edit':
                    row=clocks[idx];idx+=1
                    c=load(root/'clock.json')
                    assert c['argv']==plan['clock_command'] and c['role']==role and c['exit']==0
                    assert c['start']==int(row['start_monotonic_ns']) and c['end']==int(row['end_monotonic_ns'])
                    assert c['elapsed']==c['end']-c['start']==int(row['elapsed_ns'])
                    assert (int(row['pair']),int(row['position']),row['arm'])==(pair,pos,role)
    assert seen==load(p/'ordinary-output-verification-v2.json')=={'raw_equal_to_native_record':72,'raw_equal_to_full_stock_wild_reconstruction':24,'post_all_147_fresh':48}
    assert arm_sizes=={'R':{'0'},'F':{'1'}},arm_sizes
    print('24 ordinary clocks, 48 all-fresh repeats and all 96 complete ELF digests verified')
if __name__=='__main__':main()
