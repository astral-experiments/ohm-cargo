import json,math,os,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
from remote_common import ROOT,run,save,sha,utc
os.umask(0o077)
os.sched_setaffinity(0,set(range(24,32)))
controls=ROOT/'incoming/controls';bench=ROOT/'work/benchmark'
sys.path.insert(0,str(bench));import loader_fixture_delta as fixture
assert not (ROOT/'work/loader-fixtures/uv-loader-restack').exists()
prior=json.loads((ROOT/'records/warm-01.terminal.json').read_bytes())
assert prior['state']=='failed' and len(prior['commands'])==1 and prior['commands'][0]['returncode']==1
assert json.loads((ROOT/'logs/warm/control-tests.receipt.json').read_bytes())['returncode']==0
assert json.loads((ROOT/'records/matched-build-complete.json').read_bytes())['state']=='complete'
for p in bench.glob('*.py'):
 assert sha(p)==sha(controls/p.name)
linker=ROOT/'ohm/lib/rustlib/x86_64-unknown-linux-gnu/bin/wild-ld/ld.bfd'
assert sha(linker)=='5b2baebf62de0f8c185711b808c3f553da3b7166b1c289420df5276b027f5597'
assert linker.stat().st_size==7931512
source=ROOT/'native-template.json';template=json.loads(source.read_bytes())
missing=str(ROOT/'ohm/bin/wild');assert template['record_files'].count(missing)==1 and not Path(missing).exists()
template['record_files']=sorted(str(linker) if p==missing else p for p in template['record_files'])
save(ROOT/'native-template-02.json',template)
save(ROOT/'records/warm-02-correction.json',{'prior_terminal_sha256':sha(ROOT/'records/warm-01.terminal.json'),'prior_workload_commands':0,'old_template_sha256':sha(source),'new_template_sha256':sha(ROOT/'native-template-02.json'),'only_input_delta':{'record_file_removed':missing,'record_file_added':str(linker)},'linker_sha256':sha(linker),'fixture_absent_before':True})
environment=os.environ.copy();environment['TMPDIR']=str(ROOT/'tmp')
name = 'uv-loader-restack'
run('warm-02/initialize', ['/usr/bin/python3', '-I', '-B', str(bench / 'loader_fixture_delta.py'), 'init', '--name', name, '--template', str(ROOT / 'native-template-02.json'), '--baseline', str(ROOT / 'artifacts/baseline/cargo'), '--candidate', str(ROOT / 'artifacts/candidate/cargo'), '--copy-mode', 'copy'], env=environment)
for arm in ('candidate', 'baseline'):
    run('warm-02/seed-' + arm, ['/usr/bin/python3', '-I', '-B', str(bench / 'loader_fixture_delta.py'), 'seed', '--name', name, '--variant', arm], env=environment)

root, manifest = fixture.load(name)
records = []
for arm in ('baseline', 'candidate'):
    p = root / 'snapshots' / arm / 'manifest.json'
    row = json.loads(p.read_bytes())
    assert row['native_only'] and row['empty_live_before_seed']
    assert row['result']['returncode'] == 0
    runs = json.loads((root / 'snapshots' / arm / 'runlist.json').read_bytes())
    assert runs['rustc_invocations'] and not runs['checking_packages']
    assert all('link' in v['emit'] for v in runs['rustc_invocations'])
    expected = {'loader_injected': arm == 'baseline', 'compiler_search_directories': [''] if arm == 'baseline' else []}
    assert row['provenance'] and all(all(p[k] == v for k, v in expected.items()) for p in row['provenance']), row['provenance']
    records.append({'arm': arm, 'manifest': str(p), 'sha256': sha(p), 'rustc_invocations': len(runs['rustc_invocations']), 'provenance': row['provenance']})
save(ROOT / 'records/native-seeds-reviewed.json', {'native_only': True, 'producer_order': ['candidate', 'baseline'], 'seeds': records, 'check_commands_run': 0, 'tests_executed': False})

# Restore-only headroom rehearsal: no first-check command or comparative effect.
restores = []
for index, arm in enumerate(('baseline', 'candidate', 'candidate', 'baseline')):
    fixture.install_variant(Path(manifest['variants'][arm]), Path(manifest['canonical_executable']))
    value = fixture.prepare(name, arm, ROOT / 'excluded-restore-headroom', 'warmup', index, 0, fixture.make_environment(manifest))
    restores.append(value)
save(ROOT / 'records/excluded-restore-headroom.json', {'commands_run': 0, 'order': ['baseline', 'candidate', 'candidate', 'baseline'], 'restores': restores})
historical = json.loads((controls / 'historical-headroom.json').read_bytes())
maximum = max(r['restore_wall_ns'] for r in restores) / 1e9
margin = 10 * math.ceil((1.5 * historical['maximum_historical_pair_command_wall_ns'] / 1e9 + 2 * maximum + 20) / 10)
save(ROOT / 'records/pair-headroom.json', {'historical': historical, 'maximum_excluded_restore_seconds': maximum, 'pair_reservation_seconds': margin, 'formula': 'ceil_to_10_seconds(1.5 * historical_max_pair_command_seconds + 2 * maximum_excluded_restore_seconds + 20)', 'new_first_check_effects_observed': False})
fixture.check_inputs(manifest)
save(ROOT / 'records/warm-complete.json', {'state': 'complete', 'ended_at': utc(), 'fixture': str(root), 'source_unchanged': True, 'baseline_native_state_restored': True, 'check_commands_run': 0, 'tests_executed': False, 'pair_reservation_seconds': margin})
