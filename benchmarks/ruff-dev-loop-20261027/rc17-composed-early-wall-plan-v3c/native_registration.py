"""Bind the separately published all-width protocol and its per-occurrence source records."""
import re
import bootstrap_lineage as boot

from catalog import PHASES, digest, file_in, hashstr, must, read, sha
from continuation import HISTORICAL, WALL_PARENT

SOURCE_REF='5b9490236f0557fb748a7b7e527e45452002904b'
SOURCE_MANIFEST='d116e7b75a81b1a5b8664248ab26425cc6ed4912abf7631e8cccdb4a14c7ead7'

def check(base, manifest):
    root=base/'whole-wild-width-v2';launch=base/'wall-launch-v3c'
    source=read(root/'registration.json');published=read(launch/'catalog-publication.json')
    must(source['protocol']==manifest(root/'source')==SOURCE_MANIFEST and source['commit']==SOURCE_REF and
         published['catalog_protocol_ref']==boot.BOOT,'unexpected all-width continuation registration')
    view=read(root/'wall-view.json')
    def body(desc):
        p=file_in(root,desc['file'])
        must(sha(p)==desc['sha256'],'materialized record changed: '+desc['file'])
        return read(p)
    summary=body(view['independent_verification']);terminal=body(view['terminal'])
    must(summary['accepted'] is True and summary['admitted_or_failed_states_modified']==0 and
         summary['all_untimed_stock_wild_processes']==299*33 and summary['explicit_reported_and_plain']==299*32 and
         summary['ordinary_stock_controls']==299 and summary['workspace_linked_targets']==len(terminal)==50,
         'independent real-Wild qualification incomplete')
    must(summary['phase_occurrences']=={ph:len(view['fresh'][ph]) for ph in PHASES} and
         sum(summary['phase_occurrences'].values())==297,'independent phase coverage')
    recipes=set()
    for phase in PHASES:
        for row in view['fresh'][phase]:
            name=row['recipe']
            must(hashstr(name) and name not in recipes,'native literal occurrence reused')
            recipes.add(name)
            rule=view['targets'][row['target']]['recipes'][name]
            capture=body(row['capture']);argv=body(rule['raw_argv_file']);inputs=body(rule['raw_input_file'])
            must(rule['phase']==phase and rule['occurrence']==row['occurrence'] and
                 rule['stable_argv_sha256']==row['argv_sha256']==digest(argv)==capture['argv_sha256'] and
                 rule['inputs_sha256']==capture['inputs_sha256']==digest(inputs) and
                 name==digest([phase,capture['pid'],row['argv_sha256'],rule['inputs_sha256']]) and
                 row['raw_sha256']==capture['raw_sha256'] and capture['literal_bytes_rechecked'] is True and
                 hashstr(rule['stock_trace_set_sha256']),'literal occurrence, arguments or resolved inputs changed')
    return dict(native_protocol_ref=SOURCE_REF,native_protocol_manifest=SOURCE_MANIFEST,
                independent_plain_and_reporting=299*32,independent_ordinary_links=299,literal_recipes=len(recipes))

def publication_grant(grant, published, model, manifest, admission_sha, stopped):
    c=model['native_catalog']
    must(grant['go']=='score exact v3c 24 fresh pairs' and grant['native_sha256']==admission_sha and
         grant['plan_manifest']==manifest and grant['h5_clear'] is True and grant['other_host_measurement'] is False and
         grant['ci_review']=='accepted','wrong scoring grant or host status')
    refs=[grant[k] for k in ('published_plan','published_catalog','published_native')]
    forbidden={SOURCE_REF,boot.WALL_B,boot.BOOT,HISTORICAL['continuation_ref'],HISTORICAL['stopped_evidence_ref'],
               WALL_PARENT,stopped['protocol_ref'],stopped['result_ref']}
    must(all(re.fullmatch('[0-9a-f]{40}',x) for x in refs) and len(set(refs))==3 and not set(refs)&forbidden,
         'reused study or publication')
    must(refs[:2]==[c['plan_ref'],c['catalog_result_ref']] and grant['ci_sha256']==c['ci_sha256'] and
         c['native_protocol_ref']==SOURCE_REF and c['native_protocol_manifest']==SOURCE_MANIFEST and
         c['native_bootstrap_ref']==boot.BOOT and c['native_bootstrap_manifest']==boot.BOOT_MANIFEST and
         c['original_native_verifier_sha256']==boot.VERIFIER and c['bootstrap_startup_sha256']==boot.STARTUP_SHA and
         c['v3b_wall_ref']==boot.WALL_B and c['v3b_wall_manifest']==boot.WALL_B_MANIFEST and c['literal_recipes']==297 and c['retained_occurrences']==50 and c['new_occurrences']==249 and
         c['native_continuation_ref']==HISTORICAL['continuation_ref'] and c['native_continuation_manifest']==HISTORICAL['continuation_sha256'] and
         c['stopped_native_ref']==HISTORICAL['stopped_evidence_ref'] and c['stopped_native_manifest']==HISTORICAL['stopped_evidence_sha256'],
         'admitted source, native continuation, exact-head CI or native catalog differs')
    must(published==dict(plan_ref=refs[0],catalog_ref=refs[1],admission_ref=refs[2],plan_manifest=manifest,
                         admission_sha256=admission_sha,catalog_publication_sha256=c['registered_catalog_sha256'],
                         ci_sha256=c['ci_sha256']),'zero-clock admission was not published separately')
