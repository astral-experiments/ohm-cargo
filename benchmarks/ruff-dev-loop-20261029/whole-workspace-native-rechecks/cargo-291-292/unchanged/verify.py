#!/usr/bin/env python3
"""Verify six real-work observations, native role counts, artifact inventories, and full ELF comparisons."""
from collections import Counter
from copy import deepcopy
import gzip
import hashlib
import json
from pathlib import Path
import re
import sys

HERE = Path(__file__).resolve().parent
PHASES = ('01-empty', '02-first-unchanged', '03-second-unchanged')
HEX = re.compile('[0-9a-f]{64}')
def sha(data):
    return hashlib.sha256(data).hexdigest()

def read(name):
    data = (HERE / name).read_bytes()
    if name.endswith('.gz'):
        data = gzip.decompress(data)
    return json.loads(data)

def check(census, inventories, elfs, binding):
    fixed = {'/'.join((v['package'], v['kind'], v['target'])) for v in read('fifty-targets.json')}
    assert len(fixed) == 50
    assert set(census['arms']) == {'K', 'U'}
    assert set(elfs['cases']) <= fixed
    assert binding['source_classifier'] == '79a4b10c717ff0cf93509c99ea6ee71784b4e24dee6e2cc9e7feef1761c810e3'
    assert census['study']['locked_source'] == '93526150df078af7dd8fc4226cdcc469539d2001'
    assert census['study']['rust'] == 'ad005f99d0b51fd62b5c237bc13b31b371a1686e'
    assert census['study']['driver'] == 'ab3cffaacb292cb8ce80d7561c03409df49b7fa7d0ad6a3421b8f2a588f716d4'
    target_bodies = {k: set() for k in fixed}
    typed = set()
    summary = {}
    for arm, phases in census['arms'].items():
        assert set(phases) == set(PHASES)
        assert census['study']['arms'][arm]['source'] == {
            'K':'84af87848a5a952ba61ae6a2cc5b22da24130200',
            'U':'98d431a99779ccfbcfe42dfa74dd541de3a92d05',
        }[arm]
        summary[arm] = {}
        for phase in PHASES:
            row = phases[phase]
            typed.add(row['typed_identity'])
            assert row['typed'] == 619
            assert 0 <= row['fresh'] <= row['typed']
            if phase == '01-empty':
                assert row['fresh'] == 0
            assert set(row['targets']) == fixed
            assert row['images']['cargo'] == [census['study']['arms'][arm]['sha256']]
            assert row['images']['wild'] == [census['study']['wild']]
            assert row['real_counts']['cargo'] == 1
            assert row['real_counts']['rustc-full'] == len(row['full'])
            assert row['real_counts']['rustc-cached'] == len(row['cached'])
            assert row['real_counts']['wild'] == len(row['linkers'])
            original = row['original_display_counts']
            assert (len(row['full']) + len(row['cached']) + row['independent_rustc_probe_count']
                    == sum(original.get(k,0) for k in ('rustc-full','rustc-cached','rustc-probe')))
            assert sum(j['original_display'] == 'rustc-cached' for j in row['cached']) == original.get('rustc-cached',0)
            for job in row['full']:
                assert job['kind'] == 'full' and job['flag_encoding'] == 'full-or-probe'
                assert job['explicit_recipe_sha256'] == [] and HEX.fullmatch(job['argv_sha256'])
            for job in row['cached']:
                assert job['kind'] == 'link-only' and job['flag_encoding'] in ('split','joined')
                assert len(job['explicit_recipe_sha256']) == 1
                assert HEX.fullmatch(job['explicit_recipe_sha256'][0]) and HEX.fullmatch(job['argv_sha256'])
            refs = Counter(link['selector'] for link in row['linkers'] if link['selector'] is not None)
            assert set(refs) <= fixed and all(v == 1 for v in refs.values())
            assert all(HEX.fullmatch(li['argv_sha256']) for li in row['linkers'])
            for k, target in row['targets'].items():
                assert refs[k] == target['wild']
                if phase == '01-empty':
                    assert refs[k] == 1
                digest = inventories['roster'][k][arm+'/'+phase]
                stdout = inventories['original_stdout_by_sha256'][digest].encode()
                assert sha(stdout) == digest == target['list_sha256']
                assert sum(l.endswith(b': test') for l in stdout.splitlines()) == target['listed_tests']
                assert HEX.fullmatch(target['sha256']) and target['bytes'] == census['bodies'][target['sha256']]['bytes']
                target_bodies[k].add(target['sha256'])
            root = row['targets']['ty_server/test/e2e']
            assert root['listed_tests'] == 200 and root['list_sha256'] == census['study']['inventory']
            assert row['raw']['trace_files'] > 0
            for key in ('trace_commitment','stdout','stderr','complete','native'):
                assert HEX.fullmatch(row['raw'][key])
            summary[arm][phase] = [row['typed'], row['fresh'], len(row['full']), len(row['cached']), len(row['linkers']), sum(refs.values())]
    assert len(typed) == 1
    different = {k for k, bodies in target_bodies.items() if len(bodies) > 1}
    assert different == set(elfs['cases']) and len(different) == elfs['different_full_elf_targets']
    for key in different:
        desc = elfs['cases'][key]
        assert set(desc['bodies']) == target_bodies[key]
        for encoded, pair in desc['comparisons'].items():
            left, right = (elfs['sections'][v] for v in encoded.split())
            allsec = left['sections'].keys() | right['sections'].keys()
            changes = set()
            for k in allsec:
                a = left['sections'].get(k, {})
                b = right['sections'].get(k, {})
                if (a.get('alloc') or b.get('alloc')) and a.get('sha256') != b.get('sha256'):
                    changes.add(k)
            assert changes == set(pair['allocated_unequal_payloads'])
            assert ('.text' not in changes) == pair['text_equal']
            assert ('.rodata' not in changes) == pair['rodata_equal']
    assert binding['census'] == summary
    return summary

def reject(call, name):
    try:
        call()
    except (ValueError, KeyError, AssertionError, TypeError):
        return
    raise ValueError('accepted a mutated '+name)

def main():
    census = read('observations.json.gz')
    inventories = read('inventories.json.gz')
    elfs = read('elf-comparisons.json.gz')
    binding = read('binding.json')
    summary = check(census, inventories, elfs, binding)
    if '--self-test' in sys.argv:
        corrupt = deepcopy(census)
        corrupt['arms']['K'][PHASES[0]]['fresh'] = 1
        reject(lambda:check(corrupt,inventories,elfs,binding),'empty target')
        corrupt = deepcopy(census)
        corrupt['arms']['U'][PHASES[-1]]['real_counts']['wild'] += 1
        reject(lambda:check(corrupt,inventories,elfs,binding),'native invocation')
        corrupt = deepcopy(inventories)
        key = next(iter(corrupt['original_stdout_by_sha256']))
        corrupt['original_stdout_by_sha256'][key] += 'injected test\n'
        reject(lambda:check(census,corrupt,elfs,binding),'literal test inventory')
        corrupt = deepcopy(census)
        corrupt['arms']['K'][PHASES[0]]['full'][0]['explicit_recipe_sha256']=['0'*64]
        reject(lambda:check(corrupt,inventories,elfs,binding),'native role')
    print(json.dumps(summary,sort_keys=True))
if __name__=='__main__':
    main()
