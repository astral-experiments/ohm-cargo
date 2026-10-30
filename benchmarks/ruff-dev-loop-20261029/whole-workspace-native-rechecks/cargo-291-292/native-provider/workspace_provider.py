"""Exercise the fifty credentialed Ruff test links after a fresh ordinary workspace build."""
from collections import Counter
from pathlib import Path
import hashlib
import json
import os
import shutil
import subprocess
import tomllib

HERE = Path(__file__).resolve().parent
E2E = 'ty_server/test/e2e'
FORCED = (E2E, 'ruff_python_parser/test/generate_inline_tests', 'ty_python_semantic/lib/ty_python_semantic')
BAD = b'OHM_REJECT_BAD_WORKSPACE_TEST_LINK_SCRIPT (\n'


def selected(typed, source, target, names):
    found = {}
    for row in typed:
        if row.get('reason') != 'compiler-artifact' or not row.get('executable') or not row['profile']['test']:
            continue
        manifest = Path(row['manifest_path'])
        kind = row['target']['kind']
        if len(kind) != 1 or not manifest.is_relative_to(source):
            continue
        package = tomllib.loads(manifest.read_text())['package']['name']
        key = '/'.join((package, kind[0], row['target']['name']))
        if key in names:
            exe = Path(row['executable'])
            assert key not in found and exe.is_file() and not exe.is_symlink() and exe.resolve().is_relative_to(target)
            found[key] = exe, manifest
    assert names == set(found)
    return found


def one_output(args, exe):
    if '-o' not in args:
        return False
    path = Path(args[args.index('-o') + 1])
    return path == exe or path.is_file() and path.samefile(exe)


def run(core, work, view, out, source, env, free, memory, baseline, label):
    run = core.execute
    target = view / 'target'
    wild = view / 'sdk/lib/rustlib/x86_64-unknown-linux-gnu/bin/wild-ld/ld.bfd'
    rustc = view / 'sdk/bin/rustc'
    previous = out / '03-second-unchanged'
    names = set(baseline['selected'])
    assert len(names) == 50 and not (out / 'providers').exists()
    folder = core.mkdir(out / 'providers')
    typed = [json.loads(line) for line in (previous / 'cargo.stdout').read_bytes().splitlines()]
    current = selected(typed, source, target, names)
    assert all(core.sha(exe) == baseline['selected'][key]['sha256'] for key, (exe, _) in current.items())
    events, _, _, _ = core.collect_execs(previous / 'trace')
    argv, = [args for (image, args), n in events.items() if Path(image).is_file() and Path(image).samefile(wild) and n == 1 and one_output(args, current[E2E][0])]
    search, = [Path(v[2:]) for v in argv[:argv.index('-lgcc_s')] if v.startswith('-L') and 'psm' in Path(v[2:]).parts and Path(v[2:]).name == 'out']
    assert search.is_dir() and any(search.resolve().is_relative_to(view / root) for root in ('target', 'shared'))
    slot = search / 'libgcc_s.so'
    assert not os.path.lexists(slot)
    stock = Path(subprocess.check_output(['cc', '-print-file-name=libgcc_s.so'], env=env, text=True).strip())
    assert stock.is_absolute() and stock.is_file() and b'libgcc_s.so.1' in stock.read_bytes()
    hash0 = core.sha(stock)
    obj = view / 'tmp/ruff-checked-provider.o'
    assert not os.path.lexists(obj) and not any(ch.isspace() for ch in str(obj)+str(stock))
    assert run(['cc', '-c', HERE / 'provider.s', '-o', obj], source, env, folder, 'assemble', work, free, memory) == 0
    good = ('INPUT ( ' + str(obj) + ' ' + str(stock) + ' )\n').encode()
    history = {}
    plan = json.loads((HERE / 'control-plan.json').read_bytes())['orders']['provider50']
    try:
        for order, source_state, provider, forced in plan:
            assert source_state == 'original' and core.sha(stock) == hash0
            where = core.mkdir(folder / order)
            if os.path.lexists(slot):
                assert not slot.is_symlink() and slot.is_file() and slot.read_bytes() in (good, BAD)
                slot.unlink()
            if provider != 'absent':
                with slot.open('xb') as f:
                    f.write(good if provider == 'valid' else BAD)
            if forced:
                for i, key in enumerate(FORCED):
                    exe, _ = current[key]
                    assert not exe.is_symlink() and exe.is_file() and exe.resolve().is_relative_to(target)
                    inode = exe.stat().st_ino
                    backup = where / f'forced-{i}.elf'
                    shutil.copyfile(exe, backup)
                    assert core.sha(exe) == core.sha(backup) and exe.stat().st_ino == inode
                    exe.unlink()
            trace = core.mkdir(where / 'trace')
            rc = run(['strace','-ff','-qq','-s','524288','-e','trace=execve,execveat,exit_group','-o',trace/'exec',*core.ARGS],source,env,where,'cargo',work,free,memory)
            rows = [json.loads(line) for line in (where / 'cargo.stdout').read_bytes().splitlines()]
            ev, commitment, files, resumed = core.collect_execs(trace)
            roles = Counter()
            links = []
            for (name, args), n in ev.items():
                binary = Path(name)
                if binary.is_file() and binary.samefile(wild):
                    links.extend([args]*n)
                if binary.is_file() and binary.samefile(rustc):
                    probe = '--crate-name' not in args or any(a=='--print' or a.startswith('--print=') for a in args) and not any(a=='--emit' or a.startswith('--emit=') for a in args)
                    roles['cached' if core.classify_role(args)[0] else 'probe' if probe else 'full'] += n
            assert rc == (101 if provider == 'malformed' else 0) and rows[-1] == {'reason':'build-finished','success':rc==0} and links
            summary = {'cargo':rc,'body':{},'rustc':dict(roles),'Wild':len(links),'exec_sha256':commitment,'kernel_files':files,'resumed':resumed,'provider':provider,'forced':forced}
            if rc:
                assert BAD.split(b' (')[0] in (where/'cargo.stdout').read_bytes()+(where/'cargo.stderr').read_bytes()
            else:
                assert sum(row.get('reason')=='compiler-artifact' for row in rows)==619
                current = selected(rows,source,target,names)
                for i,(key,(exe,manifest)) in enumerate(sorted(current.items())):
                    data = core.mkdir(where/f'program-{i:02d}')
                    e = {**env,'CARGO_MANIFEST_DIR':str(manifest.parent),'CARGO_MANIFEST_PATH':str(manifest)}
                    status = run([exe,'--list'],manifest.parent,e,data,'list',work,free,memory)
                    body, listing = core.sha(exe), core.sha(data/'list.stdout')
                    if provider == 'valid':
                        assert sum(one_output(args,exe) for args in links)==1 and status==83 and not (data/'list.stdout').stat().st_size and not (data/'list.stderr').stat().st_size
                        assert body!=baseline['selected'][key]['sha256']
                    else:
                        assert status==0 and listing==baseline['selected'][key]['inventory']
                        if key==E2E:
                            for num,test in enumerate(core.TESTS):
                                tag=f'test-{num}'
                                assert run([exe,'--exact',test],manifest.parent,e,data,tag,work,free,memory)==0
                                output=(data/(tag+'.stdout')).read_bytes()
                                assert ('test '+test+' ... ok').encode() in output.splitlines() and b'199 filtered out' in output
                    summary['body'][key]=body
            core.save(where/'result.json',summary)
            history[order]=summary
            print(label,order,rc,len(links),flush=True)
        for name in names:
            def result(tag):
                return history[tag]['body'][name]
            assert result('01-native-valid')==result('03-forced-valid')!=result('02-remove')
            assert result('02-remove')==result('05-remove')==result('07-final-remove')
        assert not os.path.lexists(slot) and core.sha(stock)==hash0
        core.save(folder/'terminal.json',{'history':history,'stock_script_sha256':hash0,'provider_object':core.sha(obj)})
    finally:
        if os.path.lexists(slot):
            assert not slot.is_symlink() and slot.is_file() and slot.read_bytes() in (good,BAD)
            slot.unlink()
