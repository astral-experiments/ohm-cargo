"""Verify the native handoff on generated literal captures and deliberate inconsistencies."""
import copy
import json
from pathlib import Path
import sys
import tempfile

sys.path.insert(0,str(Path(__file__).resolve().parent))
import native_registration as native
from catalog import PHASES, digest, sha


def main():
    def save(p,x):
        p.parent.mkdir(parents=True,exist_ok=True)
        p.write_text(json.dumps(x,sort_keys=True)+'\n')
    def ref(p):
        return {'file':str(p.relative_to(root)),'sha256':sha(p)}
    with tempfile.TemporaryDirectory() as temp:
        base=Path(temp);root=base/'whole-wild-width-v1'
        save(root/'registration.json',{'protocol':native.SOURCE_MANIFEST,'commit':native.SOURCE_REF})
        save(base/'wall-launch-v3/catalog-publication.json',{'catalog_protocol_ref':native.SOURCE_REF})
        count=dict(zip(PHASES,(48,48,51,50,50,50)))
        summary={'accepted':True,'admitted_or_failed_states_modified':0,'all_untimed_stock_wild_processes':299*33,
                 'explicit_reported_and_plain':299*32,'ordinary_stock_controls':299,'workspace_linked_targets':50,
                 'phase_occurrences':count}
        save(root/'independent.json',summary)
        save(root/'terminal.json',{str(k):k for k in range(50)})
        view={'independent_verification':ref(root/'independent.json'),'terminal':ref(root/'terminal.json'),
              'targets':{},'fresh':{ph:[] for ph in PHASES}}
        argv=['ld.bfd','/tmp/coordinate','-o','/fixture/output'];inputs={'/tmp/coordinate':{'bytes':2,'sha256':'d'*64}}
        ah=digest(argv);ih=digest(inputs);save(root/'argv.json',argv);save(root/'inputs.json',inputs)
        for ph in PHASES:
            for i in range(count[ph]):
                target=str(i%50);pid=100000+i
                ident=digest([ph,pid,ah,ih]);cap=root/ident
                save(cap,{'pid':pid,'argv_sha256':ah,'inputs_sha256':ih,'raw_sha256':'c'*64,'literal_bytes_rechecked':True})
                row={'target':target,'recipe':ident,'occurrence':i//50+1,'argv_sha256':ah,'raw_sha256':'c'*64,'capture':ref(cap)}
                view['fresh'][ph].append(row)
                view['targets'].setdefault(target,{'recipes':{}})['recipes'][ident]={
                    'phase':ph,'occurrence':row['occurrence'],'stable_argv_sha256':ah,'inputs_sha256':ih,
                    'raw_argv_file':ref(root/'argv.json'),'raw_input_file':ref(root/'inputs.json'),'stock_trace_set_sha256':'a'*64}
        save(root/'wall-view.json',view)
        def run():return native.check(base,lambda p:native.SOURCE_MANIFEST)
        assert run()['literal_recipes']==297
        def refuse(fn):
            try:fn()
            except (ValueError,KeyError):return
            raise AssertionError('invalid acquisition accepted')
        def altered(fn):
            v=copy.deepcopy(view);fn(v);save(root/'wall-view.json',v);refuse(run)
        def first(v):return v['fresh'][PHASES[0]][0]
        def recipe(v):
            j=first(v);return v['targets'][j['target']]['recipes'][j['recipe']]
        altered(lambda v:recipe(v).update(phase='repeat-observer'))
        altered(lambda v:first(v).update(argv_sha256='e'*64))
        altered(lambda v:recipe(v).update(inputs_sha256='e'*64))
        altered(lambda v:first(v).update(raw_sha256='e'*64))
        altered(lambda v:recipe(v).update(occurrence=72))
        altered(lambda v:v['fresh'][PHASES[0]].__setitem__(1,first(v)))
        save(root/'wall-view.json',view)
        save(base/'wall-launch-v3/catalog-publication.json',{'catalog_protocol_ref':'a'*40});refuse(run)
        save(base/'wall-launch-v3/catalog-publication.json',{'catalog_protocol_ref':native.SOURCE_REF})
        refuse(lambda:native.check(base,lambda p:'b'*64))
        save(root/'inputs.json',{'bad':True});refuse(run)
        return {'literal_captures':297,'distinct_phases':6,'generated_data_only':True,'corrupt_bindings_rejected':9,
                'native_executions':0,'source_ref':native.SOURCE_REF,'source_manifest':native.SOURCE_MANIFEST}


if __name__=='__main__':print(json.dumps(main(),sort_keys=True,indent=2))
