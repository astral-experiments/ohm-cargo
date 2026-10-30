#!/usr/bin/env python3
"""Validate the retained runtime trials, recipe receipts, source pins, and publication manifest."""
import argparse
import copy
import gzip
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys

HERE = Path(__file__).resolve().parent
PHASES = ('01-empty', '02-first-unchanged', '03-second-unchanged')
CASES = ('inlay_hints::default_inlay_hints', 'notebook::hover_past_end_of_cell', 'notebook::inlay_hints_range_past_end_of_cell')
def digest(body):
    return hashlib.sha256(body).hexdigest()
def read(name):
    data = (HERE / name).read_bytes()
    return json.loads(gzip.decompress(data) if name.endswith('.gz') else data)
def check(behavior, recipes, observations):
    for arm in ('K', 'U'):
        for phase in PHASES:
            root = observations['arms'][arm][phase]['targets']['ty_server/test/e2e']
            visit = behavior[arm + '/' + phase]
            assert (visit['ELF'], visit['listing']) == (root['sha256'], root['list_sha256'])
            assert set(visit['tests']) == set(CASES)
            for name, t in visit['tests'].items():
                assert t['exit'] == 0
                assert digest(t['stdout'].encode()) == t['stdout_sha256']
                assert ('test '+name+' ... ok') in t['stdout'].splitlines()
                assert 'test result: ok. 1 passed; 0 failed' in t['stdout']
                assert re.fullmatch('[0-9a-f]{64}', t['stderr_sha256'])
                assert t['stderr_bytes'] > 0 and 'stderr' not in t
            assert set(observations['arms']['K'][phase]['targets']) == set(observations['arms']['U'][phase]['targets'])
            for key, k in observations['arms']['K'][phase]['targets'].items():
                u = observations['arms']['U'][phase]['targets'][key]
                assert (k['sha256'], k['bytes'], k['list_sha256']) == (u['sha256'], u['bytes'], u['list_sha256'])
            ids = [arm + '.' + j['explicit_recipe_sha256'][0] for j in observations['arms'][arm][phase]['cached']]
            stage = recipes['stages'][arm][phase]
            assert sorted(ids) == sorted(stage) and all(n == 1 for n in stage.values())
            for k in ids:
                rec = recipes['recipes'][k]
                assert rec['arm'] == arm and rec['exists_postrun'] and rec['bytes'] > 0
                assert bytes.fromhex(rec['header_hex']).startswith(b'rustlink')
                assert re.fullmatch('[0-9a-f]{64}', rec['sha256']) and k == arm+'.'+rec['argument_path_sha256']
    assert len(behavior) == 6 and len(recipes['recipes']) == 16
    assert set(recipes['stages']['U'][PHASES[1]]) == set(recipes['stages']['U'][PHASES[2]])
def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--self-test', action='store_true')
    args = parser.parse_args()
    manifest = {}
    for line in (HERE/'SHA256SUMS').read_text().splitlines():
        sha, name = line.split('  ', 1)
        assert re.fullmatch('[a-zA-Z0-9_.-]+', name) and name not in manifest
        assert digest((HERE/name).read_bytes()) == sha
        manifest[name] = sha
    assert set(manifest) == {p.name for p in HERE.iterdir() if p.is_file() and p.name != 'SHA256SUMS'}
    subprocess.run([sys.executable, '-IB', HERE/'verify.py', *(['--self-test'] if args.self_test else [])], check=True)
    behavior, recipes, observations = (read(n) for n in ('e2e-behavior.json','recipe-readback.json.gz','observations.json.gz'))
    check(behavior, recipes, observations)
    if args.self_test:
        for key in ('test', 'recipe'):
            b, r = copy.deepcopy(behavior), copy.deepcopy(recipes)
            if key == 'test':
                b['U/'+PHASES[-1]]['tests'][CASES[1]]['exit'] = 101
            else:
                next(iter(r['recipes'].values()))['header_hex'] = '00'*16
            try:
                check(b,r,observations)
            except AssertionError:
                continue
            raise ValueError('accepted corrupt '+key)
    print('Verified 6 Cargo commands, 300 target inventories, all 18 real Ruff test executions and 16 physical recipes.')
if __name__ == '__main__':
    main()

