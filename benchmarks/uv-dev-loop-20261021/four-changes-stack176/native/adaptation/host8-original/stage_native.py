#!/usr/bin/env python3
"""Stage and launch the sealed conditional host8 confirmation after all IR gates."""
import argparse
import datetime
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tarfile

SELF = Path(__file__).resolve()
HERE = SELF.parent.parent if SELF.parent.name == 'frozen' else SELF.parent
ROOT = HERE.parents[2]
REMOTE_ROOT = '/tmp/ohm-hillclimb-20261021/native-pr175-confirmation'
SSH = '/home/dev-user/.codex/skills/applied/applied-devbox/scripts/devbox_ssh'
IR_DRIVER = ROOT / 'work/benchmark/frozen/run_restacked_ir-a5326e21625b.py'
IR_DRIVER_SHA = 'a5326e21625bb701e41c6571e843ff16677c49ad785776c1ab67419aeae5ad60'
IR_SEAL_SHA = '9ff5aee1606282e928801701ac6a4fd7299ff12b15a748648ba256362c6140e9'


def now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def read(path):
    return json.loads(Path(path).read_text())


def write_once(path, value):
    if path.exists():
        old = read(path)
        assert set(old) == set(value), path
        for key in value:
            if key != 'created_at':
                assert old[key] == value[key], path
        return old
    with path.open('x') as stream:
        json.dump(value, stream, indent=2)
        stream.write('\n')
    return value


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def local_inputs():
    freeze = read(HERE / 'source-freeze.json')
    assert sha(SELF) == freeze['files']['stage_native.py']['sha256']
    driver_path = HERE / freeze['files']['native_driver.py']['frozen_path']
    assert sha(driver_path) == freeze['files']['native_driver.py']['sha256']
    native = load(driver_path, 'prospective_native_source')
    assert sha(IR_DRIVER) == IR_DRIVER_SHA
    ir = load(IR_DRIVER, 'completed_current_stack_ir')
    ir.verify_inputs()
    ir.verify_seal(IR_SEAL_SHA)
    summary = read(ir.SUMMARY)
    assert len(summary) == 4
    driver_log = ROOT / 'work/benchmark/results/restacked-current-stack-driver.log'
    events = [json.loads(line) for line in driver_log.read_text().splitlines() if line.startswith('{')]
    assert events[-1]['event'] == 'all_batches_complete' and events[-1]['native_amendment_prerequisites_met']
    files = {
        'current-stack/native_driver.py': driver_path,
        'current-stack/stage_native.py': SELF,
        'current-stack/source-freeze.json': HERE / 'source-freeze.json',
        'current-stack/schema-review.json': HERE / 'schema-review.json',
        'current-stack/gate-schema-review.json': HERE / 'gate-schema-review.json',
        'current-stack/superseded-source-freeze.json': HERE / 'source-freeze-pre-analysis-schema-fix.json',
        'current-stack/ir/input-seal.json': ir.SEAL,
        'current-stack/ir/frozen-driver.py': IR_DRIVER,
        'current-stack/ir/driver.log': driver_log,
    }
    batches = []
    for comparison, workflow, seed in ir.PLAN:
        destination = ir.paths(comparison, workflow)
        output = destination['output']
        manifest = read(output / 'manifest.json')
        integrity = read(output / 'integrity.json')
        gate = read(output / 'instruction-gate.json')
        expected = {'baseline': sha(ir.RESULTS / ('cargo-' + ir.BASELINES[comparison])),
                    'candidate': native.EXPECTED['candidate']}
        assert manifest['state'] == 'complete' and manifest['phase'] == 'confirmation'
        assert (manifest['pairs'], manifest['warmup_pairs'], manifest['seed']) == (12, 2, seed)
        assert manifest['variant_sha256'] == manifest['variant_sha256_after'] == expected
        assert manifest['recorded_file_sha256'] == manifest['recorded_file_sha256_after']
        assert integrity['state'] == 'passed' and integrity['invocations_verified'] == 28
        assert gate == ir.previous.result_gate(output) and gate['passes_instruction_gate']
        assert all(gate['gate_checks'].values())
        summary_row = next(row for row in summary if row['comparison'] == comparison and row['workflow'] == workflow)
        assert summary_row['statistics'] == gate['statistics'] and summary_row['passes_instruction_gate']
        prefix = 'current-stack/ir/' + output.name
        for name in ['manifest.json', 'samples.json', 'samples.csv', 'analysis.json', 'integrity.json', 'instruction-gate.json']:
            files[prefix + '/' + name] = output / name
        files[prefix + '/preflight-report.json'] = destination['preflight'] / 'report.json'
        batches.append({'comparison': comparison, 'workflow': workflow, 'seed': seed,
                        'integrity_state': integrity['state'], 'gate': gate,
                        'manifest_sha256': sha(output / 'manifest.json'),
                        'samples_sha256': sha(output / 'samples.json'),
                        'analysis_sha256': sha(output / 'analysis.json'),
                        'integrity_sha256': sha(output / 'integrity.json')})
    proof_path = HERE / 'ir-prerequisites.json'
    write_once(proof_path, {'created_at': now(), 'seal_sha256': IR_SEAL_SHA,
                           'all_four_gates_and_integrity_pass': True, 'batches': batches})
    files['current-stack/ir-prerequisites.json'] = proof_path
    for name in native.PROTOCOLS:
        files['current-stack/protocols/' + name] = ROOT / 'work/benchmark' / name
    for workflow, _ in native.PLAN:
        files['current-stack/base-configs/' + workflow + '.json'] = ROOT / 'work/remote-native-8/remote/benchmark' / (workflow + '-build-output-remap-loader-v2-production.json')
    for variant, name in native.NAMES.items():
        binary = ir.RESULTS / ('cargo-' + name)
        assert sha(binary) == native.EXPECTED[variant]
        files['current-stack/binaries/cargo-' + name] = binary
    for name in ir.FROZEN_FILES:
        files['current-stack/cohort/frozen/' + name] = ir.FROZEN / name
    for name in ['provenance.json', 'audit-cohort.json']:
        files['current-stack/cohort/results/' + name] = ir.RESULTS / name
    for variant in ir.TREES:
        names = [f'cargo-{variant}.build.json', f'cargo-{variant}.strip.json']
        names.extend(variant + suffix for suffix in ['.source.patch', '.stdout', '.stderr', '.occupancy.json', '.batch-status.json'])
        for name in names:
            files['current-stack/cohort/results/' + name] = ir.RESULTS / name
    assets_path = HERE / 'assets.json'
    write_once(assets_path, {'created_at': now(), 'local_ir_seal_sha256': IR_SEAL_SHA,
                            'files': {name: sha(path) for name, path in sorted(files.items())}})
    files['current-stack/assets.json'] = assets_path
    return files


RECEIVER = r'''
import hashlib,importlib.util,json,os,socket,subprocess,sys,tarfile
from pathlib import Path
root=Path(sys.argv[1]);expected=json.loads(sys.argv[2]);seen=set()
assert socket.gethostname()=='charlie-oss-8' and os.getuid()==1000
assert root.resolve()==root and root.stat().st_uid==os.getuid()
assert not (root/'native-current-stack-status.json').exists()
occupancy=subprocess.check_output(['ps','-eo','pid=,comm=,pcpu=,pmem=','--sort=-pcpu'],text=True).splitlines()
builders={'cargo','rustc','rustdoc','rust-lld','ld.lld','cc','cc1','cc1plus','clang','gcc','ninja','make','cmake','valgrind','perf'}
competing=[row for row in occupancy if row.split()[1] in builders or row.split()[1].startswith(('cargo-','callgrind-'))]
assert not competing,competing
def sha(path):
 with Path(path).open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()
with tarfile.open(fileobj=sys.stdin.buffer,mode='r|') as archive:
 for member in archive:
  assert member.isfile() and member.name in expected and member.name not in seen
  relative=Path(member.name);assert not relative.is_absolute() and '..' not in relative.parts
  destination=root/relative;assert destination.parent.resolve()==destination.parent
  destination.parent.mkdir(parents=True,exist_ok=True)
  assert destination.resolve()==destination
  data=archive.extractfile(member).read();assert hashlib.sha256(data).hexdigest()==expected[member.name]
  if destination.exists():assert destination.is_file() and sha(destination)==expected[member.name]
  else:
   with destination.open('xb') as stream:stream.write(data)
   destination.chmod(member.mode & 0o777)
  seen.add(member.name)
assert seen==set(expected)
driver=root/'current-stack/native_driver.py';seal=root/'current-stack/native-seal.json'
if seal.exists():
 spec=importlib.util.spec_from_file_location('native_staged_check',driver);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
 module.load_core();module.verify_assets();module.verify_seal(sha(seal))
else:
 with (root/'current-stack/seal-prepare.stdout').open('xb') as out,(root/'current-stack/seal-prepare.stderr').open('xb') as err:
  subprocess.run([sys.executable,str(driver),'--prepare'],stdout=out,stderr=err,check=True)
record={'state':'sealed; no current-stack Cargo executed on host8','seal_sha256':sha(seal),'assets_sha256':sha(root/'current-stack/assets.json'),'files_verified':len(expected),'hostname':socket.gethostname(),'uid':os.getuid(),'occupancy_before_transfer':occupancy[:20]}
print(json.dumps(record,indent=2))
'''


LAUNCHER = r'''
import datetime,hashlib,json,shlex,socket,subprocess,sys
from pathlib import Path
root=Path(sys.argv[1]);expected=sys.argv[2];socket_name='ohm-current-stack-native-20261021';session='confirmation'
assert socket.gethostname()=='charlie-oss-8'
seal=root/'current-stack/native-seal.json';assert hashlib.sha256(seal.read_bytes()).hexdigest()==expected
assert not (root/'native-current-stack-status.json').exists()
assert not (root/'current-stack/launch.json').exists()
probe=subprocess.run(['tmux','-L',socket_name,'has-session','-t',session],capture_output=True)
assert probe.returncode!=0,'Existing task tmux session must be preserved'
log=root/'logs/current-stack-native-driver.log';assert not log.exists()
argv=['taskset','-c','8',sys.executable,str(root/'current-stack/native_driver.py'),'--run','--sealed-inputs-sha256',expected]
command='exec '+shlex.join(argv)+' > '+shlex.quote(str(log))+' 2>&1'
subprocess.run(['tmux','-L',socket_name,'-f','/dev/null','new-session','-d','-s',session,command],check=True)
record={'launched_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'tmux_socket':socket_name,'tmux_session':session,'argv':argv,'log':str(log),'seal_sha256':expected,'hostname':socket.gethostname()}
with (root/'current-stack/launch.json').open('x') as stream:json.dump(record,stream,indent=2);stream.write('\n')
print(json.dumps(record,indent=2))
'''


def stage():
    files = local_inputs()
    expected = {name: sha(path) for name, path in files.items()}
    write_once(HERE / 'transfer-sha256.json', expected)
    assert not (HERE / 'native-stage-receipt.json').exists()
    with (HERE / 'transfer.stderr').open('xb') as errors:
        process = subprocess.Popen([SSH, 'charlie-oss-8', '--', 'python3', '-c', RECEIVER, REMOTE_ROOT, json.dumps(expected)],
                                   stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=errors)
        try:
            with tarfile.open(fileobj=process.stdin, mode='w|') as archive:
                for name, path in files.items():
                    assert path.is_file() and not path.is_symlink()
                    archive.add(path, arcname=name, recursive=False)
        finally:
            process.stdin.close()
        output = process.stdout.read()
        code = process.wait()
    (HERE / 'transfer.stdout').write_bytes(output)
    assert code == 0, code
    receipt = json.loads(output)
    assert receipt['files_verified'] == len(files) and receipt['assets_sha256'] == sha(HERE / 'assets.json')
    write_once(HERE / 'native-stage-receipt.json', receipt)
    print(json.dumps(receipt, indent=2))


def launch():
    local_inputs()
    receipt = read(HERE / 'native-stage-receipt.json')
    assert receipt['assets_sha256'] == sha(HERE / 'assets.json')
    assert not (HERE / 'native-launch-receipt.json').exists()
    with (HERE / 'launch.stderr').open('xb') as errors:
        result = subprocess.run([SSH, 'charlie-oss-8', '--', 'python3', '-c', LAUNCHER, REMOTE_ROOT, receipt['seal_sha256']],
                                stdout=subprocess.PIPE, stderr=errors)
    (HERE / 'launch.stdout').write_bytes(result.stdout)
    result.check_returncode()
    record = json.loads(result.stdout)
    write_once(HERE / 'native-launch-receipt.json', record)
    print(json.dumps(record, indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument('--stage', action='store_true')
    action.add_argument('--launch', action='store_true')
    args = parser.parse_args()
    if args.stage:
        stage()
    else:
        launch()


if __name__ == '__main__':
    main()
