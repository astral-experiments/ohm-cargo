import importlib.util
import json
import os
from pathlib import Path
import shutil
import stat
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))
from remote_common import ROOT, run, save, sha, utc

os.umask(0o077)
os.sched_setaffinity(0, set(range(24, 32)))
assert json.loads((ROOT / 'records/setup-complete.json').read_bytes())['state'] == 'complete'
source = ROOT / 'producer/source'
stock = ROOT / 'tools/stock'
tmp = ROOT / 'producer/tmp'
tmp.mkdir()
env = {k: os.environ[k] for k in ('HOME', 'USER', 'LOGNAME', 'SHELL', 'LANG', 'LC_ALL', 'TZ') if k in os.environ}
env.update({
    'CARGO_HOME': str(ROOT / 'producer/cargo-home'),
    'CARGO_TARGET_DIR': str(ROOT / 'producer/target'),
    'RUSTC': str(stock / 'bin/rustc'), 'RUSTDOC': str(stock / 'bin/rustdoc'),
    'PATH': str(stock / 'bin') + ':/usr/bin:/bin',
    'CARGO_BUILD_JOBS': '8', 'CARGO_INCREMENTAL': '0', 'CARGO_TERM_COLOR': 'never',
    'CARGO_PROFILE_RELEASE_LTO': 'thin', 'CARGO_PROFILE_RELEASE_CODEGEN_UNITS': '1',
    'CARGO_PROFILE_RELEASE_DEBUG': '1', 'CARGO_PROFILE_RELEASE_OPT_LEVEL': '3',
    'CARGO_PROFILE_RELEASE_INCREMENTAL': 'false', 'CARGO_PROFILE_RELEASE_STRIP': 'none',
    'CFG_RELEASE_CHANNEL': 'dev', 'LIBZ_SYS_STATIC': '1', 'TMPDIR': str(tmp),
    'SSL_CERT_FILE': '/etc/ssl/certs/ca-certificates.crt', 'SSL_CERT_DIR': '/usr/lib/ssl/certs',
    'GIT_CONFIG_GLOBAL': str(ROOT / 'control/gitconfig'),
})
command = [str(stock / 'bin/cargo'), 'build', '--release', '--locked', '--bin', 'cargo', '--features', 'all-static,ohm-defaults', '-j', '8', '-v']
save(ROOT / 'records/matched-build-recipe.json', {'argv': command, 'cwd': str(source), 'environment': env, 'cpu_affinity': sorted(os.sched_getaffinity(0)), 'embedded_head': '5e5d271d763d7beb38b48755e22bd59e93f02b97', 'pgo': False, 'builds': ['baseline', 'candidate']})
helper = ROOT / 'incoming/controls/strip_binaries.py'
spec = importlib.util.spec_from_file_location('original_strip', helper)
strip = importlib.util.module_from_spec(spec)
spec.loader.exec_module(strip)
tool_paths = [stock / 'bin/cargo', stock / 'bin/rustc', stock / 'bin/rustdoc', stock / 'lib/librustc_driver-999a121de2f042be.so', Path('/usr/bin/objcopy'), Path('/usr/bin/cc'), Path('/usr/bin/c++'), Path('/usr/bin/ld'), Path('/usr/bin/cmake'), Path('/usr/bin/pkg-config'), Path('/usr/bin/git')]
tools_before = [{'path': str(p), 'resolved': str(p.resolve()), 'sha256': sha(p), 'bytes': p.stat().st_size} for p in tool_paths]
save(ROOT / 'records/build-tools-before.json', tools_before)
artifacts = ROOT / 'artifacts'
artifacts.mkdir()
results = []
for arm, tree, commit in (
    ('baseline', '6919395c3f4732ade7d263db1d5b64fd7562845e', 'ff1eacd2b577777ecb8a7f3e934ddac36d11928e'),
    ('candidate', '45280a180bb4bea53c79d423c7cc71255dfe81c3', '8fbefabb23d1b1950b9e5d224ed986ada7331192'),
):
    prefix = 'build/' + arm
    run(prefix + '-reset', ['/usr/bin/git', 'reset', '--hard', '5e5d271d763d7beb38b48755e22bd59e93f02b97'], cwd=source, env=env)
    run(prefix + '-apply-base', ['/usr/bin/git', 'apply', '--index', str(ROOT / 'incoming/patches/base.patch')], cwd=source, env=env)
    if arm == 'candidate':
        run(prefix + '-apply-loader', ['/usr/bin/git', 'apply', '--index', str(ROOT / 'incoming/patches/loader.patch')], cwd=source, env=env)
    observed_tree = run(prefix + '-tree', ['/usr/bin/git', 'write-tree'], cwd=source, env=env).decode().strip()
    assert observed_tree == tree
    assert run(prefix + '-head', ['/usr/bin/git', 'rev-parse', 'HEAD'], cwd=source, env=env).decode().strip() == '5e5d271d763d7beb38b48755e22bd59e93f02b97'
    run(prefix + '-index-clean', ['/usr/bin/git', 'diff', '--exit-code'], cwd=source, env=env)
    assert not run(prefix + '-untracked', ['/usr/bin/git', 'ls-files', '--others', '--exclude-standard'], cwd=source, env=env)
    run(prefix + '-source-patch', ['/usr/bin/git', 'diff', '--cached', '--binary', '--full-index', 'HEAD'], cwd=source, env=env)
    assert sha(source / 'Cargo.lock') == 'c49cc3e6fb251810e84f945711ef5c7e4dab57ab395918873133a3704c3fc2f3'
    run(prefix + '-production', command, cwd=source, env=env)
    destination = artifacts / arm
    destination.mkdir()
    full = destination / 'cargo.full'
    stripped = destination / 'cargo'
    shutil.copy2(ROOT / 'producer/target/release/cargo', full)
    original = full.read_bytes()
    run(prefix + '-strip', ['/usr/bin/objcopy', '--strip-debug', str(full), str(stripped)], env=env)
    assert full.read_bytes() == original
    allocated = strip.allocated_sections(original)
    assert strip.allocated_sections(stripped.read_bytes()) == allocated
    os.chmod(full, 0o755)
    os.chmod(stripped, 0o755)
    version = run(prefix + '-version', [str(stripped), '-Vv'], env=env)
    linked = run(prefix + '-ldd', ['/usr/bin/ldd', str(stripped)], env=env).decode()
    dependencies = []
    for line in linked.splitlines():
        words = line.split()
        path = words[2] if len(words) >= 3 and words[1] == '=>' else words[0] if words and words[0].startswith('/') else None
        if path:
            p = Path(path)
            dependencies.append({'path': path, 'resolved': str(p.resolve()), 'sha256': sha(p), 'bytes': p.stat().st_size})
    result = {'arm': arm, 'source_commit': commit, 'source_tree': tree, 'embedded_head': '5e5d271d763d7beb38b48755e22bd59e93f02b97', 'full': {'path': str(full), 'bytes': full.stat().st_size, 'mode': stat.S_IMODE(full.stat().st_mode), 'sha256': sha(full)}, 'stripped': {'path': str(stripped), 'bytes': stripped.stat().st_size, 'mode': stat.S_IMODE(stripped.stat().st_mode), 'sha256': sha(stripped)}, 'version_stdout_sha256': __import__('hashlib').sha256(version).hexdigest(), 'allocated_sections': allocated, 'dynamic_libraries': dependencies}
    save(destination / 'identity.json', result)
    results.append(result)
    assert run(prefix + '-tree-after', ['/usr/bin/git', 'write-tree'], cwd=source, env=env).decode().strip() == tree
    run(prefix + '-index-clean-after', ['/usr/bin/git', 'diff', '--exit-code'], cwd=source, env=env)
    print(json.dumps({'arm': arm, 'state': 'archived', 'sha256': result['stripped']['sha256']}), flush=True)
tools_after = [{'path': str(p), 'resolved': str(p.resolve()), 'sha256': sha(p), 'bytes': p.stat().st_size} for p in tool_paths]
save(ROOT / 'records/build-tools-after.json', tools_after)
assert tools_before == tools_after
assert results[0]['version_stdout_sha256'] == results[1]['version_stdout_sha256']
assert results[0]['dynamic_libraries'] == results[1]['dynamic_libraries']
save(ROOT / 'records/matched-build-complete.json', {'state': 'complete', 'ended_at': utc(), 'artifacts': results, 'tools_unchanged': True, 'same_version_stdout': True, 'same_dynamic_libraries': True})
