"""Recover from a stale native proc-macro expansion by changing one tracked option on one compiler."""
from pathlib import Path
import argparse, hashlib, json, os, shutil, subprocess


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def main():
    args = argparse.ArgumentParser()
    args.add_argument('--sdk', required=True, type=Path)
    args.add_argument('--root', required=True, type=Path)
    args.add_argument('--fixture', required=True, type=Path)
    a = args.parse_args()
    a.root.mkdir()
    rustup = a.root / 'rustup'
    (rustup / 'toolchains').mkdir(parents=True)
    (rustup / 'toolchains/ohm').symlink_to(a.sdk)
    for name in ['native.rs', 'reader.rs']:
        shutil.copyfile(a.fixture/name, a.root/name)
    env = dict(PATH=os.environ['PATH'], RUSTUP_HOME=str(rustup), HOME=str(a.root), LANG='C.UTF-8', RUSTUP_AUTO_INSTALL='0')
    rows = {}

    def call(label, command):
        run = subprocess.run(command, cwd=a.root, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=60, check=True)
        rows[label] = dict(argv=command, exit=run.returncode, stdout=run.stdout.decode(), stderr=run.stderr.decode())
        return run

    assert Path(call('sysroot', ['rustc', '+ohm', '--print', 'sysroot']).stdout.decode().strip()).samefile(a.sdk)
    inputs = {}
    for phase, expect, change, enabled, cache, ran in [
        ('original', 17, 17, 'yes', 'warm', True),
        ('original-again', 17, None, 'yes', 'warm', False),
        ('edited', 17, 29, 'yes', 'warm', False),
        ('edited-again', 17, None, 'yes', 'warm', False),
        ('first-disabled', 29, None, 'no', 'warm', True),
        ('disabled-again', 29, None, 'no', 'warm', True),
        ('empty-enabled', 29, None, 'yes', 'empty', True),
    ]:
        if change is not None:
            (a.root/'native.c').write_text(f'int value(void) {{ return {change}; }}\n')
            call(phase+'-cc', ['cc', '-fPIC', '-c', 'native.c', '-o', 'native.o'])
            call(phase+'-macro', ['rustc', '+ohm', 'native.rs', '-Clink-arg=native.o'])
        inputs[phase] = {name:sha(a.root/name) for name in ['native.rs','reader.rs','native.c','native.o','libnative.so']}
        c = call(phase, ['rustc', '+ohm', 'reader.rs', '--extern', 'native=libnative.so', '-Zcache-proc-macros='+enabled, '-C', 'incremental='+cache, '-o', 'result'])
        r = call(phase+'-run', ['./result'])
        assert r.stdout.decode().strip()==f'{expect},{expect}' and not r.stderr
        assert sorted(c.stderr.decode().splitlines()) == ([f'ran attribute {expect}', f'ran derive {expect}'] if ran else [])
        rows[phase]['executable']=sha(a.root/'result')
    after = [inputs[n] for n in ['edited','edited-again','first-disabled','disabled-again','empty-enabled']]
    assert all(a==after[0] for a in after)
    assert rows['first-disabled']['executable']==rows['disabled-again']['executable']==rows['empty-enabled']['executable']
    assert rows['first-disabled']['argv']==[x.replace('-Zcache-proc-macros=yes','-Zcache-proc-macros=no') for x in rows['edited-again']['argv']]
    record=dict(rows=rows, inputs=inputs, frontend=sha(a.sdk/'bin/rustc'), driver=sha(next((a.sdk/'lib').glob('librustc_driver-*.so'))))
    (a.root/'terminal.json').write_text(json.dumps(record, sort_keys=True, indent=2)+'\n')

if __name__=='__main__':
    main()
