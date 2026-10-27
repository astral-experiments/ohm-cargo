"""Independently verify old/candidate states, native rosters, exact encoded-record transitions and API probes."""
import collections,gzip,hashlib,json
from pathlib import Path
p=Path(__file__).resolve().parent
rdata=json.loads((p/'results.json').read_text());bindings=json.loads((p/'clone-bindings.json').read_text());oldtool=json.loads((p/'official16.json').read_text());sha=lambda b:hashlib.sha256(b).hexdigest()
old='42e90992cec21a29956e20fd52ab952472a9dbc1dcc7a3b60c92aad101b5f568';new='d7dfa671c8ec6ca2b50c7b0e41af4c0046e19bc02f18145d97d98455af2f722c'
assert sha((p/'plan.json').read_bytes())==json.loads((p/'study.json').read_text())['plan_sha256']
def cell(m,s,t):return json.loads(gzip.decompress((p/(m+'-'+s+'-'+t+'.json.gz')).read_bytes()))
def quick(z):return {k:z['receipt']['physical'].get(k,0)for k in ('rustc-full','rustc-link-only','wild','build-script')}
def roster(z):
    return sorted(json.dumps({k:a[k]for k in a if k!='fresh'},sort_keys=True)for a in z['unit-roster'])
def echo(r):
    cols=('exit','stdout_sha','stderr_sha','names','error_message')
    return {k:{n:r[k][n]for n in cols if n in r[k]}for k in r}
def assert_shape(n,z,stock_cold_test=False):
    assert z['receipt']['exit']==0
    assert z['receipt']['units']==len(z['unit-roster'])==n
    assert z['receipt']['fresh']==sum(a['fresh']for a in z['unit-roster'])
    assert z['receipt']['physical']==dict(collections.Counter(c['role']for c in z['all-physical-typed-processes']))
    direct=[c for c in z['all-physical-typed-processes']if c['role']in ('rustc-full','rustc-link-only','wild')]
    failures=[c for c in direct if c['exit']!=0]
    if stock_cold_test:
        assert len(failures)==1 and failures[0]['role']=='rustc-full' and failures[0]['crate']=='integration_test' and failures[0]['exit']==1
        assert any(c['pid']>failures[0]['pid']and c['arg_sha256']==failures[0]['arg_sha256']and c['exit']==0 for c in direct)
    else:assert not failures
    assert z['receipt']['driver']==oldtool['driver']and z['receipt']['compiler']==oldtool['frontend']and z['receipt']['linker']==oldtool['wild']
def check():
    report={}
    for mode,n,cs,mtime,obs in [('check',520,71,449,0),('build',501,68,433,0),('test',619,162,456,1)]:
        assert set(bindings[mode])=={'seed-tree','stock-repeat-input-tree','upgraded-input-tree'}
        assert len({z['sha256']for z in bindings[mode].values()})==1
        cold=cell(mode,'seed','cold');assert_shape(n,cold,mode=='test');assert cold['receipt']['fresh']==0 and cold['wire-records']is None
        settled=cell(mode,'seed','noop-2'if mode=='test'else'noop-1');assert_shape(n,settled)
        assert settled['receipt']['fresh']==n and sum(quick(settled).values())==0
        if mode=='test':
            born=cell(mode,'seed','noop-1');assert born['receipt']['fresh']==563 and quick(born)=={'rustc-full':1,'rustc-link-only':50,'wild':50,'build-script':0}
        wire=settled['wire-records'];assert wire['counts']=={'ordinary-mtime':mtime,'legacy-ordinary-checksum-retrain':cs,**({'obs1-safe-complete':obs}if obs else {})}
        assert not any(v.get('space_names',0)for v in wire['rows'].values())
        cmp=settled['products'];ran={}
        for arm in ('stock-repeat','upgraded'):
            for t in ('first','second','third-if-displaced'):
                f=p/(mode+'-'+arm+'-'+t+'.json.gz')
                if t=='third-if-displaced'and not f.exists():continue
                z=cell(mode,arm,t);assert_shape(n,z)
                assert roster(z)==roster(settled)
                ctool=old if arm=='stock-repeat'else new;assert z['receipt']['cargo_image']==ctool
                ods={k:{'before':cmp.get(k),'after':z['products'].get(k)}for k in cmp.keys()|z['products'].keys()if cmp.get(k)!=z['products'].get(k)}
                assert ods==z['changed-products']
                fs=z['wire-records']['rows'];wr=collections.Counter((v['class'],fs[k]['class']if k in fs else 'absent')for k,v in wire['rows'].items()if k not in fs or v['sha256']!=fs[k]['sha256'])
                assert {':'.join(u):w for u,w in wr.items()}==z['compiler-record-joins']['mutated_records_by_before_after_class']
                jobs=z['compiler-record-joins']['physical'];orig=collections.Counter(j['role']for j in jobs)
                assert all((j['exit']==0 and j['before_class']!='unmapped')for j in jobs),(mode,arm,t,[j for j in jobs if j['before_class']=='unmapped'][:1])
                for k in ('rustc-full','rustc-link-only'):assert orig.get(k,0)==z['receipt']['physical'].get(k,0)
                seen={};reads=z['ordinary-readers']
                if arm=='stock-repeat'and t=='first':
                    expected_reader=echo(reads);gold=reads
                assert echo(reads)==expected_reader,(mode,arm,t)
                if mode=='check':assert gold['ordinary-error']['primary']==reads['ordinary-error']['primary'] and gold['ordinary-error']['secondary']==reads['ordinary-error']['secondary']
                if arm=='stock-repeat':
                    assert z['receipt']['fresh']==n and not ods and sum(quick(z).values())==0 and wire['rows']==fs
                if arm=='upgraded':
                    ran[t]={'fresh':z['receipt']['fresh'],'native':quick(z),'mutated_class':z['compiler-record-joins']['mutated_records_by_before_after_class'],'remaining_classes':z['wire-records']['counts'],'raw_products_changed':len(ods),'ELF_changed':sum((v['before']or{}).get('elf',False)or(v['after']or{}).get('elf',False)for v in ods.values()),'ordinary_semantic_oracles_equal':True}
        report[mode]=ran
    return report
if __name__=='__main__':print(json.dumps(check(),sort_keys=True,indent=2))
