#!/usr/bin/env python3
"""Reconstruct a per-target proof from three immutable published packets and the archived native exec observations."""
import argparse
import collections
import gzip
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tarfile

REFS = {
    'queue': ('46767bab62f2cb4295410150ecbd77d4a12320fd', 'rc19-native-queue-opportunity-h8'),
    'release': ('3ec6efbb651be21e2227b8ee33f701fb011a2fc8', 'rc18-release-ruff-link-census'),
    'corner': ('6680c887512650c45d2e877a0b73383ea288c8ce', 'rc18-exact-rlib-native-boundary'),
}
NATIVE = ('gcc', 'collect2', 'stock-wild')
E2E = 'e2e-f978f73ba5a3a2ed'

def h(value):
    return hashlib.sha256(value).hexdigest()

def uniq(rows):
    data = {x['target']: x for x in rows}
    assert len(data) == len(rows)
    return data

def roots(argv):
    result = {}
    for i, x in enumerate(argv):
        if not x.startswith('-L'):
            continue
        value = Path(argv[i + 1] if x == '-L' else x[2:])
        if value.name == 'out':
            package = value.parts[-3]
            assert package not in result and package in {'psm', 'zstd-sys'}
            result[package] = i
    return result

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('git_checkout')
    parser.add_argument('physical_queue_reports', type=Path)
    parser.add_argument('released_e2e_capsule', type=Path)
    args = parser.parse_args()
    sources = {}
    def published(component, name):
        rev, packet = REFS[component]
        spec = rev + ':benchmarks/ruff-dev-loop-20261027/' + packet + '/' + name
        raw = subprocess.check_output(['git', '-C', args.git_checkout, 'cat-file', 'blob', spec])
        sources[component + '/' + name] = h(raw)
        return raw
    def data(component, name):
        raw = published(component, name)
        return json.loads(gzip.decompress(raw) if name.endswith('.gz') else raw)

    records = data('release', 'release.json')
    custody = data('release', 'custody/summary.json')
    custody_rows = uniq(data('release', 'custody/targets.json'))
    assert custody['target_count'] == custody['targets_with_an_earlier_absent_libgcc_s_so_under_the_user_changeable_psm_build_directory'] == 50
    assert custody['independent_higher_provider_directories_for_that_specific_name'] == 1
    assert custody['distinct_search_directory_spellings']['build_user_changeable'] == 5
    component_ctl = data('release', 'single-archive/summary.json')
    h8_raw = data('queue', 'raw.json')
    subject = data('queue', 'identity.json')
    assert subject['ruff'] == records['subject']['source'] and not subject['old_release_artifact_word_for_word']
    body = records['active_shadow']
    before = uniq(body['before'])
    roster = set(before)
    phases = {r['phase']: r for r in body['phases']}
    valid, invalid, restored = (phases[s] for s in ('valid','invalid','restored'))
    assert [(r['cargo_exit'], r['native_link_execs']) for r in (valid, invalid, restored)] == [(0,50),(101,8),(0,50)]
    assert invalid['malformed_diagnostic'] and valid['exit_83'] == 50 and restored['exit_83'] == 0
    valid_so = uniq(valid['outputs'])
    restored_so = uniq(restored['outputs'])
    official = {k: uniq(records['live_native_captures'][k]['records']) for k in ('inner', 'outer')}
    trace = {k: uniq(v['processes']['successful_native_execs']) for k,v in phases.items()}
    assert len(roster) == 50 and all(set(src) == roster for src in (custody_rows, valid_so, restored_so, *official.values(), trace['valid'], trace['restored']))
    assert len(trace['invalid']) == 8 and set(trace['invalid']) < roster
    out = {}
    for target in sorted(roster):
        v = valid_so[target]
        a = before[target]
        b = restored_so[target]
        assert v['list_exit'] == 83 and v['list_count'] == 0 and v['list_sha256'] == h(b'') and v['hook_symbol']
        assert not a['hook_symbol'] and not b['hook_symbol'] and a['sha256'] == b['sha256'] and v['sha256'] != a['sha256']
        assert len({v['namespace'], a['namespace'], b['namespace'], body['mask_namespace']}) == 1
        for k in official:
            c = official[k][target]
            assert c['output_namespace'] == c['search_namespace']
            assert records['live_native_captures'][k]['stock_linker'] == records['active_shadow']['wild']
        assert official['inner'][target]['scope'] == official['outer'][target]['scope']
        assert official['inner'][target]['raw_exec_sha256'] == custody_rows[target]['physical_exec_record_sha256']
        out[target] = {
            'package': official['inner'][target]['scope'],
            'official_native_exec_sha256':{k:official[k][target]['raw_exec_sha256'] for k in official},
            'official_shadow_wild_exec_trace_sha256':{k: t[target]['trace_sha256'] for k,t in trace.items() if target in t},
            'official_elf_original_sha256': a['sha256'], 'official_elf_shadow_sha256':v['sha256'],
            'official_elf_restored_sha256':b['sha256'], 'official_valid_libgcc_shadow_list_exit':v['list_exit'],
            'official_earlier_libgcc_s_so_absent_in_writable_psm_census': True,
            'original_wild_psm_libutil_a_enoent_syscall': None,
            'sealed_e2e_replay_negative_libutil_links':None,
            'ron_edge_in_queue_runs':{},'full_native_exec_argv':{}
        }

    for n in (1,2,3):
        key = 'instrumented' + str(n)
        q = data('queue', key + '.json.gz')
        links = uniq(data('queue', key + '-links.json.gz')['links'])
        assert set(links)==roster
        reg = {e[1]:e for _,e in q['events'] if e[0]=='register'}
        ron, = [x[1] for x in reg.values() if x[2:5] == ['ron','ron','Build']]
        for target, link in links.items():
            e = reg[link['unit']]
            assert e[2:6] == [link['pkg'], link['name'], 'Test', link['kind']]
            assert out[target]['package'].replace('-','_')==link['pkg'].replace('-','_')
            assert [p for p in e[7] if p[0]==ron] == [[ron,'All']]
            kind = json.loads(e[5])
            if isinstance(kind,list):
                kind, = kind
            for k,v in (('name',e[3]),('kind',kind)):
                assert out[target].setdefault(k,v)==v
            out[target]['ron_edge_in_queue_runs'][key]=[e[1], ron,'All']
        if n==2:
            assert 'native.json' not in h8_raw[key]
            continue
        raw = (args.physical_queue_reports / key / 'native.json').read_bytes()
        assert h(raw) == h8_raw[key]['native.json']
        sources[key+'/native.json'] = h(raw)
        origin = json.loads(raw)
        assert origin['images']['cargo']['sha256']==subject['diagnostic_cargo']
        assert origin['images']['stock-wild']['sha256']==records['active_shadow']['wild']
        assert origin['images']['rustc']['sha256']=='c6ab483d6698f68eebb49d74b27361f3e02ede55452dc0416c3fdec9a45b7f60'
        families = {t:{} for t in roster}
        for e in origin['events']:
            if e['role'] not in NATIVE:
                continue
            target = Path(e['out']).name
            assert e['role'] not in families[target]
            assert origin['process_exit'][str(e['pid'])]==0
            a = e['argv']
            assert h(b'\0'.join(map(os.fsencode,a))+b'\0')==e['argv_sha256']
            assert a.count('-lutil')==1 and a.count('-lgcc_s')==1 and a[a.index('-o')+1]==e['out']
            families[target][e['role']]=e
        for target, f in families.items():
            assert set(f)==set(NATIVE)
            assert f['gcc']['pid']==f['collect2']['ppid'] and f['collect2']['pid']==f['stock-wild']['ppid']
            packages = roots(f['stock-wild']['argv'])
            assert 'psm' in packages and all(set(roots(e['argv']))==set(packages) for e in f.values())
            av=f['stock-wild']['argv']
            system = min(i for i,v in enumerate(av) if v.startswith(('-L/usr/lib','-L/lib/')))
            assert all(pos<system for pos in packages.values()) and av[av.index('-lutil')-2:av.index('-lutil')]==['-Bdynamic','-lgcc_s']
            out[target]['full_native_exec_argv'][key]={r:{'native_argv_sha256':f[r]['argv_sha256'],'lutil_index':f[r]['argv'].index('-lutil')} for r in NATIVE}
            direct_ron = [op for op in av if Path(op).name.startswith('libron-') and op.endswith('.rlib')]
            assert len(direct_ron)<=1
            assert out[target].setdefault('wild_direct_libron_archive',bool(direct_ron))==bool(direct_ron)
            assert out[target].setdefault('cargo_build_script_search_roots',sorted(packages))==sorted(packages)
            out[target]['full_native_exec_argv'][key]['wild_search_indices']={**packages,'first_system':system}
    assert collections.Counter(r['kind'] for r in out.values())=={'test':30,'lib':17,'bin':3}
    assert sum('zstd-sys' in r['cargo_build_script_search_roots'] for r in out.values())==34
    assert sum(r['wild_direct_libron_archive'] for r in out.values())==35
    assert out[E2E]['wild_direct_libron_archive'] and out[E2E]['package']=='ty_server' and 'zstd-sys' in out[E2E]['cargo_build_script_search_roots']

    capsule = args.released_e2e_capsule.read_bytes()
    import io
    with tarfile.open(fileobj=io.BytesIO(capsule),mode='r:gz') as ar:
        training=component_ctl['outcome']['training']
        raw=ar.extractfile('recipes/'+training+'.json').read()
    assert h(raw)==training
    recipe=json.loads(raw)
    assert recipe['kernel_file_observations_sha256']==component_ctl['kernel_reads_sha256']
    assert recipe['source']==custody['inputs_manifest_sha256']
    assert recipe['capture']==official['inner'][E2E]['raw_exec_sha256']
    assert recipe['program_sha256']==official['inner'][E2E]['sha256'] and recipe['out'].endswith('/'+E2E)
    positive=[row for row in recipe['wire'] if Path(row[0]).name=='libutil.a' and row[4]==0]
    assert positive
    shadows=[]
    for root in ('psm','zstd-sys'):
        for name in ('libutil.a','libutil.so'):
            entries=[row for row in recipe['wire'] if Path(row[0]).name==name and root in Path(row[0]).parts]
            assert len(entries)==1 and entries[0][1:]==['','',0,1]
            shadows.append(root+'/out/'+name)
    out[E2E]['sealed_e2e_replay_negative_libutil_links']=shadows
    corner_manifest = published('corner','SHA256SUMS').decode()
    corner_raw = published('corner','h2-native-selected.tar.gz')
    assert h(corner_raw)+'  h2-native-selected.tar.gz' in corner_manifest
    with tarfile.open(fileobj=io.BytesIO(corner_raw),mode='r:gz') as ar:
        c=json.load(ar.extractfile('v4/reports/all.json'))
        corner_phases=('repeat','earlier-provider','removed-provider','same-size-time-native')
        hits=[c[phase]['actual'] for phase in corner_phases]
        assert hits==['native-value=41','native-value=83','native-value=41','native-value=83']
        assert len({c[phase]['files']['rlib']['sha256'] for phase in corner_phases})==1
        for phase in ('earlier-provider','removed-provider','same-size-time-native'):
            assert c[phase]['files']['executable']['sha256']==c[phase+'-empty']['files']['executable']['sha256']
        for phase, verdict in [('repeat','ENOENT'),('earlier-provider','O_RDONLY|O_CLOEXEC) = ')]:
            base='v4/reports/'+phase+'/'
            x=json.load(ar.extractfile(base+'native-observations.json'))
            path=x['selected_new_archive']['path']
            assert Path(path).name=='libutil.a'
            calls=[e for e in x['lookups'] if path in e['text'] and verdict in e['text']]
            assert calls
            assert any(ar.extractfile(base+'exec.'+str(e['tid'])).read().decode().splitlines()[e['line']-1]==e['text'] for e in calls)
    result={
        'schema':1, 'commits':REFS, 'source_sha256':sources,'instrumented_cargo_sha256':subject['diagnostic_cargo'],
        'official_inner_file_census_sha256':custody['private_physical_census_gzip_sha256'],
        'official_e2e_separate_closed_replay':{'recipe_sha256':training,'kernel_observations_sha256':recipe['kernel_file_observations_sha256'],'existing_capsule_sha256':h(capsule)},
        'summary':{'targets':50,'other_than_ty_server_e2e':49,'lutil_in_entire_gcc_collect2_wild_chains_in_each_of_two_runs':50,
            'wild_direct_libron_archive':35,'wild_no_direct_libron_archive':15,'psm_search':50,'additional_zstd_search':34,'other_49_psm':49,'other_49_zstd':33,
            'ordinary_per_link_libutil_a_enoent_event_unknown':50,
            'separate_replayed_wild_negative_wire_targets':1,'valid_libgcc_provider_actual_ruff_elf_list_exit_83':50,
            'malformed_libgcc_provider_actual_native_jobs_before_abort':8,'malformed_cargo_exit':101,'restored_original_ELFs':50},
        'targets':out}
    print(json.dumps(result,sort_keys=True,separators=(',',':')))
if __name__=='__main__':
    main()
