"""Project the original archived files without publishing host paths or private source endpoints."""

from collections import Counter
import gzip
import hashlib
import json
from pathlib import Path
import re
import runpy
import subprocess
import sys
import tarfile

HERE = Path(__file__).resolve().parent
NATIVE = runpy.run_path(str(HERE / 'native_execs.py'))
PIN = '93526150df078af7dd8fc4226cdcc469539d2001'
HIST = '6dc1031889aa24a0461457409d39861e279242a9'


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def json_file(path):
    return json.loads(path.read_bytes())


def emit(path, value):
    raw = (json.dumps(value, indent=2, sort_keys=True, ensure_ascii=True) + '\n').encode()
    path.write_bytes(gzip.compress(raw, mtime=0) if path.suffix == '.gz' else raw)


def verify_archive(archive, extracted):
    with tarfile.open(archive) as tar:
        members = tar.getmembers()
        names = {m.name for m in members}
        assert len(members) == len(names)
        observed = {f.relative_to(extracted).as_posix() for f in extracted.rglob('*') if f.is_file()}
        assert names == observed
        for member in members:
            assert member.isfile() and not Path(member.name).is_absolute() and '..' not in Path(member.name).parts
            assert tar.extractfile(member).read() == (extracted / member.name).read_bytes()
    return {'members': len(names), 'bytes': archive.stat().st_size, 'sha256': sha(archive.read_bytes())}


def normal(text, view):
    text = text.replace(view, '<arena>')
    # The source ID names a public registry; its on-disk replacement bucket is site-specific.
    return re.sub(r'(<arena>/cargo-home/registry/src/)[^/" ]+', r'\1<bucket>', text)


def main(root, out, ruff):
    roots = {v: verify_archive(root / f'h8-native-{v}.tgz', root / f'h8-rows-{v}') for v in ['v1']}
    actual = root / 'h8-rows-v1'
    assert (actual / 'exit').read_text().strip() == '0'
    warm_trace=(actual/'toml-test-v1/C/00-prepare.exec').read_text()
    runtime_roots=set(re.findall(r'execve\("([^"]+?)/lib/rustlib/[^/"]+/bin/wild-ld/ld[.]bfd"',warm_trace))
    assert len(runtime_roots)==1
    runtime_root,=runtime_roots
    assert (actual / 'bench.py').read_bytes() == (root / 'bench.py').read_bytes()
    evidence = {'archives': roots, 'modes': {}}
    for mode in ['build', 'test']:
        d = actual / ('toml-' + mode + '-v1')
        terminal = json_file(d / 'terminal.json')
        assert terminal['mode'] == mode and len(terminal['events']) == 128
        result = {'terminal': terminal, 'raw_terminal_sha256': sha((d / 'terminal.json').read_bytes()),
                  'controls': {}, 'enrollments': {}, 'slots': {}}
        for arm in 'CAB':
            a = d / arm
            enrolled = json_file(a / 'enrollment.json')
            view = str(Path(enrolled['env']['RUSTUP_HOME']).parent)
            assert all(enrolled['env'][v].startswith(view + '/') for v in ['CARGO_HOME','CARGO_TARGET_DIR','CARGO_BUILD_BUILD_DIR'])
            env = {k: normal(v, view) for k, v in enrolled.pop('env').items()}
            env['PATH'] = env['PATH'].replace(env['HOME'] + '/.cargo/bin', '<rustup-proxies>')
            env.update(HOME='<home>', USER='<user>', LOGNAME='<user>')
            result['enrollments'][arm] = {**enrolled, 'environment': env,
                                         'raw_sha256':sha((a/'enrollment.json').read_bytes())}
            for raw_report in sorted(a.glob('*.jsonl')):
                tag = raw_report.stem
                raw_worker = a / (tag + '.json')
                full = json_file(raw_worker)
                raw_tb = (a / (tag + '.exec')).read_bytes()
                raw_err = (a / (tag + '.stderr')).read_bytes()
                def scrub_trace(text):
                    text=normal(text,view)
                    text=text.replace(str(Path(json_file(a/'enrollment.json')['env']['HOME'])/'.cargo/bin'),'<rustup-proxies>')
                    text=text.replace(runtime_root+'/lib/rustlib/','<runtime>/lib/rustlib/')
                    return text
                public_stdout=normal(raw_report.read_text(),view)
                reports = [json.loads(line) for line in public_stdout.splitlines()]
                observed = NATIVE['native_execs'](raw_tb)
                result['controls'][arm + '/' + tag] = {
                    'stdout':public_stdout,'trace':scrub_trace(raw_tb.decode()),'worker_roster':json.loads(normal(json.dumps(full['roster']),view)),'reports': reports, 'processes': observed, 'files': full['files'], 'oracle': full['oracle'],
                    'worker_exec_summary': full['exec'], 'worker_dirty_targets': full['dirty'],
                    'raw_worker_sha256': sha(raw_worker.read_bytes()), 'raw_stdout_sha256': sha(raw_report.read_bytes()),
                    'raw_trace_sha256': sha(raw_tb), 'raw_stderr_sha256': sha(raw_err),
                    'stderr': normal(raw_err.decode(),view),
                }
            if arm != 'C':
                for i in range(32):
                    for phase in ['edit','repeat']:
                        tag = f'{i:02}-{phase}'
                        raw = a / (tag+'.json')
                        record = json_file(raw)
                        stdout = (a/(tag+'.stdout')).read_bytes()
                        stderr = (a/(tag+'.stderr')).read_bytes()
                        assert not stdout and sha(stdout) == record['stdout'] and sha(stderr) == record['stderr']
                        norm = normal(stderr.decode(),view)
                        result['slots'][arm+'/'+tag] = {'native_row':record, 'raw_record_sha256':sha(raw.read_bytes()),
                                                       'stdout':'','stderr':norm,'normalized_stderr_sha256':sha(norm.encode())}
        evidence['modes'][mode]=result
    independent=json_file(root/'complete-native-execs.json')
    all_controls={}
    for mode,mode_data in evidence['modes'].items():
        for tag,item in mode_data['controls'].items():
            es=item['processes']
            all_controls[f'toml-{mode}-v1/{tag}.exec']={
                'count':len(es),'files':len(item['files']),'links':sum(NATIVE['is_link'](q) for q in es),
                'oracle':item['oracle'],'programs':dict(Counter(q['program'] for q in es)),
                'roster':sum(r['reason']=='compiler-artifact' for r in item['reports']),
                'sha256':item['raw_trace_sha256'],'source_rustc':sum(NATIVE['is_compile'](q) for q in es)}
    assert independent==all_controls
    evidence['original_complete_exec_capture_sha256']=sha((root/'complete-native-execs.json').read_bytes())
    emit(out/'wall-native.json.gz',evidence)
    files={p.relative_to(actual).as_posix():{'bytes':p.stat().st_size,'sha256':sha(p.read_bytes())}
           for p in sorted(actual.rglob('*')) if p.is_file()}
    emit(out/'raw-file-index.json.gz',files)
    def git(*args):
        return subprocess.check_output(['git','-C',ruff,*args])
    manifest = git('show',PIN+':Cargo.toml')
    lock = git('show',PIN+':Cargo.lock')
    hist = git('show','--format=',HIST,'--','Cargo.toml')
    (out/'ruff-Cargo.toml.gz').write_bytes(gzip.compress(manifest,mtime=0))
    (out/'ruff-Cargo.lock.gz').write_bytes(gzip.compress(lock,mtime=0))
    (out/'historical.patch').write_bytes(hist)
    (out/'RUFF-LICENSE').write_bytes(git('show',PIN+':LICENSE'))
    import tomllib
    trial = json_file(actual/'receipt.json')
    roles = ('source','tree','git_parent','baseline','baseline_binary','cargo_sha256','pgo_profile','ordered_external_inputs',
             'independent_native_files','independent_rlibs','product_diff','baseline_to_git_parent_delta','literal_compiler_commands_equal')
    subjects = {'build': {k: trial[k] for k in roles},'ruff':PIN,'historical':HIST,'patch_sha256':sha(hist),
                'lock_sha256':sha(lock),'lock_bytes':len(lock),'locked_packages':len(tomllib.loads(lock.decode())['package']),
                'original_manifest_sha256':sha(manifest),'ruff_license_sha256':sha((out/'RUFF-LICENSE').read_bytes()),
                'ruff_license_blob':git('rev-parse',PIN+':LICENSE').decode().strip(),
                'hardware':{'OS':'Linux x86-64','logical_cpus':[0,1,2,3],'account':'unprivileged','effective_capabilities':0,
                            'home_and_durable_free_GiB_each':24,'tmpfs_free_GiB':16,'four_pair_order':['AB','BA','BA','AB']},
                'raw_version':sha((actual/'receipt.json').read_bytes()),'original_design_sha256':sha((root/'design.md').read_bytes()),
                'original_driver_sha256':sha((actual/'bench.py').read_bytes()),'original_analysis_sha256':sha((root/'analyze.py').read_bytes()),
                'original_analytical_result_sha256':sha((root/'paired-wall.json').read_bytes()),
                'native_roles_receipt_sha256':sha((root/'complete-native-execs.json').read_bytes())}
    emit(out/'subjects.json',subjects)
    (out/'design.md').write_bytes((root/'design.md').read_bytes())
    (out/'reported-statistics.json').write_bytes((root/'paired-wall.json').read_bytes())
    (out/'analyze.py').write_bytes((root/'analyze.py').read_bytes())


if __name__ == '__main__':
    main(*(Path(p).resolve() for p in sys.argv[1:]))
