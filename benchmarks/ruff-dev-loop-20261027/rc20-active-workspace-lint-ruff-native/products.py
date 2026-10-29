"""Compare Cargo JSON products using target identity across physical toolchain layers."""
import argparse,gzip,json
from pathlib import Path

HERE=Path(__file__).resolve().parent

def typed(rec):
    result={}; hashes=rec['row']['products']; paths=set()
    for msg in map(json.loads,rec['streams']['stdout'].splitlines()):
        if msg['reason']!='compiler-artifact': continue
        for filename in msg['filenames']:
            assert filename.startswith('<arena>/'); rel=filename.removeprefix('<arena>/')
            key=(msg['package_id'],msg['target']['name'],tuple(msg['target']['kind']),Path(filename).suffix)
            assert key not in result and rel not in paths
            result[key]=hashes[rel]; paths.add(rel)
    assert paths==set(hashes)
    return result

def compare(source):
    pairs={}
    def pair(key,left,right):
        a=typed(left);b=typed(right);assert a.keys()==b.keys()
        pairs[key]={'total':len(a),'different':[{'package':p,'target':n,'kind':k,'extension':e,'left':a[(p,n,k,e)],'right':b[(p,n,k,e)]} for p,n,k,e in sorted(a) if a[(p,n,k,e)]!=b[(p,n,k,e)]]}
    for arm in 'AB':
        for mode in ['check','build','test']:
            for k,l,r in [('edited','03-reverse','05-clean-edited'),('restored','08-restored','01-original')]:
                key='/'.join([arm,mode,k]); pair(key,source[arm][mode+'-'+l],source[arm][mode+'-'+r]); ds=pairs[key]['different']
                assert [(x['target'],x['extension']) for x in ds]==([] if mode=='check' else [('ruff_text_size','.rlib')])
    for name,a in source['A'].items():pair('A-vs-B/'+name,a,source['B'][name])
    return pairs

if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--captures',type=Path,default=HERE);root=ap.parse_args().captures
    data=json.loads(gzip.decompress((root/'streams.json.gz').read_bytes()));pairs=compare(data)
    published=root/'products.json'; calculated=json.dumps(pairs,indent=2,sort_keys=True)+'\n'
    if published.exists(): assert published.read_text()==calculated
    else:published.write_text(calculated)
    print('Compared both 28-command arms and all 12 edited or restored references.')
