"""Read the previously acquired root-only ELF recipes through the new admission checks."""
import copy
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
from common import *
from run_wall import OLD
from wire import check,disk,sha

def run():
    expected=get(DESIGN/'whole-reference.json')['sources'];passed={};neg=[]
    for a in ('parent','child'):
        for lane,m,phase in (('warm-'+a,'original','restore'),('leaf-'+a+'-original','original','root-empty'),('leaf-'+a+'-edited','edited','root-empty')):
            d=OLD/'reports'/lane/phase;vol=OLD/'lanes'/lane;raw=disk(OLD/'recipe-forensics/raw'/(lane+'.rlink'));ledger=get(d/'root-current-recipe.json');j=get(d/'native.json');n,=[v for v in j['events'] if v['role']=='stock-wild' and v['out']==str(E2E)];assert j['process_exit'][str(n['pid'])]==0
            native={o['path']:(o['size'],o['sha256']) for o in n['direct_file_operands']}
            inc=(vol/'state-upper'/INC.relative_to(LIVE)) if lane.startswith('warm-')else(vol/'empty-incremental')
            obj=(vol/'state-upper'/E2E.with_suffix('.rlink-objects').relative_to(LIVE))if lane.startswith('warm-')else(vol/'empty-unit/out'/E2E.with_suffix('.rlink-objects').name)
            v=check(raw,ledger,expected[m],inc,obj,native)
            passed[lane]={'body':v['body'],'strict':v['same_history_wire'],'general':v['all_histories_wire'],'raw_cfg':v['raw_cfg'],'mask':v['cache_mask'],'current_objects':v['absolute_current_object_identifiers'],'native_sources':sum(v['cache_mask'])}
            if lane=='leaf-parent-edited':
                def reject(name,body,source,inputs):
                    try:check(bytes(body),source,expected[m],inc,obj,inputs)
                    except (AssertionError,ValueError):neg.append(name)
                    else:raise AssertionError('accepted corruption '+name)
                for label,index in (('undecoded opaque payload',(len(raw)*4)//5),('registered span endpoint',v['raw_span_ledger'][0]['offset']),('output nonce',len(raw)-22)):
                    t=bytearray(raw);t[index]^=1;g=copy.deepcopy(ledger);g['source_sha256']=sha(t);reject(label,t,g,native)
                key=next(str(obj) for obj in native if obj.endswith('.rcgu.o'));fp=native[key];fake=dict(native);fake[key]=(fp[0],'0'*64);reject('kernel object content',raw,ledger,fake)
        assert len(passed)==(3 if a=='parent'else 6)
    for p,c in [('warm-parent','warm-child')]+[('leaf-parent-'+m,'leaf-child-'+m) for m in ('original','edited')]:
        assert all(passed[p][k]==passed[c][k]for k in ('strict','general','raw_cfg','mask','current_objects'))
    assert len(neg)==4 and sorted(q['native_sources']for q in passed.values())==[0,0,0,0,135,135]
    result={'source':'retained six genuine prior H/P root recipes with still-extant object backing','checked_partial':{k:{i:q[i] for i in ('body','strict','general','current_objects','native_sources')}for k,q in passed.items()},'rejected':neg,'no_new_cargo':True,'new_pairs':0}
    print(json.dumps(result,sort_keys=True,indent=2))
if __name__=='__main__':run()
