"""Admit concrete native outputs from independently published per-input real Wild replays."""
import collections
import gzip
import hashlib
import json
from pathlib import Path
import re
from elf import fingerprint

PHASES=('seed-repeat1','seed-repeat2','selected-observer','repeat-observer','selected-composed','repeat-composed')

def sha(file):
    with file.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def read(path):return json.loads(path.read_bytes())
def digest(x):return hashlib.sha256(json.dumps(x,separators=(',',':'),sort_keys=True).encode()).hexdigest()
def hashstr(value):return isinstance(value,str) and bool(re.fullmatch('[a-f0-9]{64}',value))
def gitref(value):return isinstance(value,str) and bool(re.fullmatch('[a-f0-9]{40}',value))
def must(test,message):
    if not test:raise ValueError(message)

def file_in(root,relative):
    p=Path(relative)
    must(not p.is_absolute() and '..' not in p.parts,'unsafe capture path')
    f=root/p
    must(f.resolve().is_relative_to(root.resolve()) and f.is_file() and not f.is_symlink(),'missing or unsafe capture: '+relative)
    return f

def check_ci(plan,rows):
    ci=plan['composed_ci']
    must(isinstance(rows,list) and len(rows)==2,'both exact-head CI receipts required')
    for role in ('observer','composed'):
        expected=ci[role]
        pair=[r for r in rows if r['number']==expected['number']]
        must(len(pair)==1 and pair[0]['head']==expected['head'],'unexpected CI head or duplicate PR')
        row=pair[0]
        must(row['url']==f"https://github.com/astral-sh/ohm-cargo/pull/{expected['number']}",'wrong CI repository')
        checks=row['checks'];names=[x['name'] for x in checks]
        must(len(names)==len(set(names)) and set(ci['required_checks'])<=set(names),'missing or duplicate applicable CI')
        for c in checks:
            must(re.fullmatch(r'https://github.com/astral-sh/ohm-cargo/actions/runs/[0-9]+/job/[0-9]+',c['detailsUrl']),'check has no exact Actions job')
            ok=(c['conclusion']=='SUCCESS' or (c['name'] in ci['explicitly_inapplicable_checks'] and c['conclusion']=='SKIPPED'))
            must(c['status']=='COMPLETED' and ok,'incomplete or failing CI: '+c['name'])

def expected_kind(phase,path):
    package=path.split('/')[-4]
    if phase.startswith('selected-') and package=='ty_server' and (Path(path).name.startswith('ty_server-') or Path(path).name.startswith('e2e-')):
        return 'full'
    return 'link-only'

def catalog_view(root,view,historical,plan,prior,phase_outputs,failed_hashes,raw_body=fingerprint):
    """Return the exact raw allowlist after checking all named phases, inputs, widths and ELF bytes."""
    scope=plan['catalog_scope']
    must(view['schema']==1 and view['wild_sha256']==plan['sdk']['tools']['wild'] and view['wild_source']==scope['public_wild_source'],'wrong Wild source/image')
    must(view['cpu']==plan['cpu'] and view['jobs']==plan['jobs'] and view['widths']==scope['widths'] and
         view['native_ref']==scope['native_reference'],'different affinity, job count, widths or native evidence')
    must(set(historical)==set(view['historical'])==set(view['fresh'])==set(phase_outputs)==set(PHASES),'native phase coverage')
    checked_files={}
    def witness(desc):
        path=desc['file'];h=desc['sha256']
        if path not in checked_files:checked_files[path]=sha(file_in(root,path))
        must(checked_files[path]==h,'source receipt bytes changed: '+path)
    for key in ('terminal','independent_verification'):witness(view[key])
    required=set();families=collections.defaultdict(set);natural=collections.defaultdict(set);phasefamilies=collections.defaultdict(set)
    for ph in PHASES:
        order=lambda rows:sorted((j['target'],j['exec_sha256'],j['argv_sha256']) for j in rows)
        must(order(historical[ph])==order(view['historical'][ph]),'historical true Wild identity: '+ph)
        rows=view['fresh'][ph];expected=collections.Counter(j['target'] for j in historical[ph])
        must(collections.Counter(j['target'] for j in rows)==expected,'new true Wild target multiplicity: '+ph)
        # Raw exec hashes can coincide for identical argv; independently captured occurrence receipts must differ.
        must(len({(j['target'],j['capture']['file'],j.get('occurrence',j['exec_sha256'])) for j in rows})==len(rows),'duplicate capture occurrence: '+ph)
        required.update(expected)
        for j in rows:
            t=j['target'];recipe=j['recipe']
            must(j['kind']==expected_kind(ph,t) and j['exit']==0 and j['wild_sha256']==view['wild_sha256'] and all(hashstr(j[k]) for k in ('exec_sha256','argv_sha256','raw_sha256')),'new native link mode or receipt: '+t)
            witness(j['capture']);families[t].add(recipe);natural[t,recipe].add(j['raw_sha256']);phasefamilies[ph,t].add(recipe)
    must(sum(len(v) for v in historical.values())==scope['historical_wild_occurrences'] and
         len(required)==scope['directly_linked'] and required==set(view['targets']) and required<=set(prior),'complete linked target census')
    allowed={t:set(old) for t,old in prior.items()};byrecipe={};widths=scope['widths']
    must(len(allowed)==scope['output_files'] and sum(t not in required and len(v)==1 for t,v in allowed.items())==scope['unchanged_exact'],'uninvolved outputs must stay singleton')
    for t in sorted(required):
        target=view['targets'][t];witness(target['evidence'])
        must(set(target['recipes'])==families[t] and bool(families[t]),'extra or missing native recipe: '+t)
        normalized=set();union=set();shapes=set();seen_bodies={}
        for name,recipe in target['recipes'].items():
            ident=(recipe['inputs_sha256'],recipe['stable_argv_sha256'])
            must(all(hashstr(x) for x in ident) and ident not in shapes,'missing or duplicate operand family: '+t);shapes.add(ident)
            sweeps=recipe['widths']
            must(sorted(row['width'] for row in sweeps)==widths,'missing or repeated worker width: '+t)
            values=set()
            for row in sweeps:
                h=row['plain_sha256']
                must(row['plain_exit']==0 and row['depfile_exit']==0 and hashstr(h) and h==row['depfile_sha256'],'plain/reported Wild disagreement: '+t)
                values.add(h)
            must(natural[t,name]<=values and set(recipe['bodies'])==values,'unexplained default output or missing physical ELF: '+t)
            for h,p in recipe['bodies'].items():
                if h not in seen_bodies:
                    f=file_in(root,p);must(sha(f)==h,'unexpected physical stock output: '+t)
                    shape=raw_body(f);seen_bodies[h]=(shape['normalized'],shape['bytes'])
                normalized.add(seen_bodies[h])
            byrecipe[t,name]=values;union.update(values)
        must(len(normalized)==1 and allowed[t]<=union,'unexplained bytes or original variant was lost: '+t)
        allowed[t]=union
    for ph in PHASES:
        for t in {j['target'] for j in historical[ph]}:
            candidates=set().union(*(byrecipe[t,k] for k in phasefamilies[ph,t]))
            must(phase_outputs[ph][t] in candidates,'historical whole output missing from same phase: '+ph+' '+t)
    for t,h in failed_hashes.items():
        candidates=set().union(*(byrecipe[t,k] for k in phasefamilies['repeat-observer',t]))
        must(h in candidates,'previously rejected raw file not reproduced by matching control repeat: '+t)
    return {t:sorted(hs) for t,hs in allowed.items()}


def publication(base,here,manifest,plan):
    launch=base/'wall-launch-v3';binding=read(launch/'binding.json')
    must(set(binding)=={'ref','sha256'} and gitref(binding['ref']) and binding['sha256']==manifest,'v3 registration must have been published and read back')
    must(binding['ref'] not in {plan['native_commit'],plan['stopped_v2']['protocol_ref'],plan['stopped_v2']['result_ref']},'earlier study registration reused')
    published=read(launch/'catalog-publication.json')
    must(published['plan_ref']==binding['ref'] and published['plan_manifest']==manifest and published['native_reference']==plan['catalog_scope']['native_reference'],'catalog does not bind published v3 study')
    ids=(binding['ref'],published['catalog_protocol_ref'],published['catalog_result_ref'])
    must(all(gitref(v) for v in ids) and len(set(ids))==3 and published['independent_review']=='accepted','catalog requires separate published source and native result')
    root=base/'whole-wild-width-v1'
    for path,key in [('wall-view.json','view_sha256'),('terminal.json','terminal_sha256')]:
        must(sha(root/path)==published[key],'published catalog content changed: '+path)
    view=read(root/'wall-view.json')
    must(view['terminal']=={'file':'terminal.json','sha256':published['terminal_sha256']} and
         view['independent_verification']['sha256']==published['verifier_receipt_sha256'],'different catalog terminal/independent reader')
    check_ci(plan,read(here/'ci-exact-heads.json'))
    check_ci(plan,read(launch/'ci.json'))
    return root,view,dict(plan_ref=binding['ref'],catalog_protocol_ref=ids[1],catalog_result_ref=ids[2],
                          registered_catalog_sha256=sha(launch/'catalog-publication.json'),catalog_view_sha256=published['view_sha256'],
                          terminal_sha256=published['terminal_sha256'],independent_verification_sha256=published['verifier_receipt_sha256'],
                          ci_sha256=sha(launch/'ci.json'))


def qualify(n,g):
    """Combine the physically checked native v3 sources with the separately reviewed catalog."""
    plan=g.P;scope=plan['catalog_scope'];base=g.BASE
    root,view,seal=publication(base,g.HERE,g.manifest(g.HERE),plan)
    # The older qualified guards verify the published compiler and linker traces, native process
    # reduction, all 376 separate first-selection snapshots, both terminal outputs and prior widths.
    m=g.evidence(n)
    old=base/'early-scheduler-wall-admission-v2.json'
    must(sha(old)==plan['stopped_v2']['native_admission'] and read(old)['native']==m,'changed earlier zero-clock native admission')
    frozen=g.HERE/'historical-links.json.gz'
    must(sha(frozen)==scope['historical_catalog_roster_sha256'],'historical roster input changed')
    historical=json.loads(gzip.decompress(frozen.read_bytes()))
    must(historical['canonical']==str(n.can) and historical['native_manifest']==scope['native_result_manifest'] and historical['native_reference']==scope['native_reference'],'wrong historical input packet')
    def logical(path):
        p=Path(path).relative_to(n.can)
        must(p.parts[0] in ('target','shared') and '..' not in p.parts,'unexpected physical native target')
        return str(p)
    archived=historical['phases'];actual={};outputs={}
    for ph in PHASES:
        d=n.w/ph;jobs=read(d/'physical.json')
        actual[ph]=[{'target':logical(j['target']),'exec_sha256':j['raw'],'argv_sha256':digest(j['argv'])} for j in jobs if j['kind']=='wild']
        expected=lambda z:sorted((r['target'],r['exec_sha256'],r['argv_sha256']) for r in z)
        must(expected(actual[ph])==expected(archived[ph]),'historical physical occurrence differs from published census: '+ph)
        outputs[ph]={logical(p):h for p,h in read(d/'products.json')['native'].items()}
    prior={logical(p):set(hashes) for p,hashes in m['allowed'].items()}
    stopped=base/'early-scheduler-wall-rc17-v2';stop=plan['stopped_v2']
    must(sha(stopped/'first-failure.txt')==stop['first_failure_sha256'],'stopped v2 exception changed')
    # Only its failed native bytes are admitted as negative controls. The old clocks are never opened.
    failed={p:stop['unadmitted'][Path(p).name] for p in prior if Path(p).name in stop['unadmitted']}
    must(len(failed)==len(stop['unadmitted'])==2,'stopped output identities')
    for name,h in failed.items():
        must(sha(n.actual(str(n.can/name),stopped/'02-2-B/private-state'))==h and h not in prior[name],'failed native ELF not retained or already admitted')
    result=catalog_view(root,view,actual,plan,prior,outputs,failed)
    evidence={**seal,'widths':scope['widths'],'linked_targets':scope['directly_linked'],
              'exact_others':scope['unchanged_exact'],'historical_occurrences':sum(map(len,actual.values())),
              'fresh_occurrences':sum(map(len,view['fresh'].values())),
              'input_families':sum(len(t['recipes']) for t in view['targets'].values()),
              'raw_sha256_sets':digest(result),'prior_failure_sha256':stop['first_failure_sha256']}
    return {**m,'allowed':{str(n.can/p):hs for p,hs in result.items()},'native_catalog':evidence}
