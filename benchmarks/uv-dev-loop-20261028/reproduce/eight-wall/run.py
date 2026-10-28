#!/usr/bin/env python3
"""Time only successful native Cargo commands on two paired, pre-audited private test targets."""
import argparse
import collections
import csv
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from edit_holdout import BEFORE, EDIT_PATH
from edit_toolchain import elf, switch
from measure import BENCH, RUST, WORK, digest


def save(path, obj):
    with path.open('x') as f:
        f.write(json.dumps(obj, indent=2) + '\n')


def copy(src, dest):
    if os.path.lexists(dest):
        raise RuntimeError(f'occupied destination: {dest}')
    subprocess.run(['cp', '-a', '--reflink=auto', str(src), str(dest)], check=True)


def snapshot(tree):
    h = hashlib.sha256()
    count = size = 0
    for p in sorted(tree.rglob('*')):
        s = p.lstat()
        if p.is_file() and not p.is_symlink():
            count += 1
            size += s.st_size
        entry = [str(p.relative_to(tree)), s.st_mode, s.st_mtime_ns, os.readlink(p) if p.is_symlink() else s.st_size if p.is_file() else 0]
        h.update(json.dumps(entry).encode() + b'\n')
    return dict(files=count, bytes=size, metadata_sha256=h.hexdigest(), rustc_info_sha256=digest(tree/'.rustc_info.json'))


def observe_exec(log, slot, rustc, linker):
    # strace -v exposes full argv. Only the explicit, credential-free experiment environment is inherited.
    counts = collections.Counter()
    roles = {'cargo':[], 'rustc':[], 'wild':[]}
    selected = {str(slot): 'cargo', str(rustc): 'rustc', str(linker): 'wild'}
    decoder = json.JSONDecoder()
    for path in log.glob('exec.*'):
        for line in path.read_text(errors='strict').splitlines():
            if not re.search(r'= 0$', line):
                continue
            match = re.match(r'^execve\(("(?:\\.|[^"\\])*"),\s*', line)
            if not match:
                raise ValueError(f'unresolved successful exec in {path}: {line[:120]}')
            exe = json.loads(match[1])
            counts[exe] += 1
            if exe not in selected:
                if Path(exe).name in {'cargo','rustc','wild','wild-ld','ld','ld.bfd','ld.lld','rust-lld'}:
                    raise ValueError(f'unexpected tool path: {exe}')
                continue
            argv, _ = decoder.raw_decode(line[match.end():])
            if not isinstance(argv,list):
                raise ValueError(f'failed to obtain full argv for {exe}')
            role = selected[exe]
            if role == 'wild':
                if '--no-fork' in argv or '--fork' in argv or '-o' not in argv:
                    raise ValueError(f'non-default or unidentified linker invocation: {argv[:4]}')
                roles[role].append(argv[argv.index('-o')+1])
            else:
                roles[role].append(argv)
    for values in roles.values():
        values.sort()
    if {k:len(v) for k,v in roles.items()} != {'cargo':1,'rustc':6,'wild':5}:
        raise ValueError(f'unexpected native exec roster: {dict(counts)}')
    save(log/'native-execs.json', counts)
    save(log/'roles.json', roles)
    return roles


def live_group(pgid):
    found = []
    for f in Path('/proc').glob('[0-9]*/stat'):
        try:
            fields = f.read_text().rsplit(')',1)[1].split()
        except (FileNotFoundError, ProcessLookupError):
            continue
        if fields[0] not in ('Z','X') and int(fields[2]) == pgid:
            found.append(int(f.parent.name))
    return found


def main():
    p = argparse.ArgumentParser()
    p.add_argument('phase', choices=('warm','measure','post-audit'))
    p.add_argument('cohort', choices=('initial','replica'))
    a = p.parse_args()
    plan = json.loads((HERE/'plan.json').read_text())
    cfg = plan['cohorts'][a.cohort]
    prior = json.loads((WORK/f"edit-holdout-{cfg['fixture']}/test/protocol.json").read_text())
    root = BENCH/f"edit-{cfg['fixture']}-test"
    sysroot = BENCH/f"sysroot-edit-{cfg['fixture']}-test"
    source, target, slot = root/'source', root/'target', root/'bin/cargo'
    rustc, linker = sysroot/'bin/rustc', sysroot/plan['linker_slot']
    global_linker = RUST.parent/plan['linker_slot']
    scratch = root/'eight-wall'
    out = HERE/'results'/a.cohort
    expect_cpu = plan['preparation_cpus'] if a.phase == 'warm' else plan['native_cpus']
    if sorted(os.sched_getaffinity(0)) != expect_cpu:
        raise ValueError(f'{a.phase} expects CPUs {expect_cpu}')
    if a.phase == 'warm':
        out.mkdir(parents=True, exist_ok=False)
        scratch.mkdir(mode=0o700)
    lock = (scratch/'lease').open('a')
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    if a.phase == 'measure':
        quiet = HERE/'quiet'/f'{a.cohort}-ready.json'
        if (os.environ.get('OHM_EIGHT_NATIVE_RELEASED') != 'yes' or not quiet.is_file()
                or not json.loads(quiet.read_text())['quiet'] or time.time()-quiet.stat().st_mtime > 60):
            raise RuntimeError('a fresh successful preflight and explicit coordinator release are required')
    if (prior['uv'] != plan['uv'] or Path(prior['source']) != source or os.path.lexists(target)
            or linker.samefile(global_linker) or elf(rustc) != plan['rustc_sha256']
            or elf(RUST/'rustc') != plan['rustc_sha256'] or elf(global_linker) != plan['release_wild_sha256']):
        raise ValueError('wrong or occupied fixture or toolchain')
    old = {'cargo':scratch/'prior-cargo','wild':scratch/'prior-wild'}
    if a.phase == 'warm':
        os.link(slot,old['cargo'])
        os.link(linker,old['wild'])
    if not slot.samefile(old['cargo']) or not linker.samefile(old['wild']):
        raise ValueError('previous private fixture selections were not restored')
    actual = {arm:{k:(WORK/v[0]).resolve() for k,v in pair.items()} for arm,pair in plan['arms'].items()}
    identity = {arm:{k:elf(path) for k,path in pair.items()} for arm,pair in actual.items()}
    if identity != {arm:{k:v[1] for k,v in pair.items()} for arm,pair in plan['arms'].items()}:
        raise ValueError('registered binary hash changed')
    audit = json.loads((WORK/'pgo-confirmation-v2/audit.json').read_text())
    if any(audit['arms'][key]['cargo_sha256'] != identity[arm]['cargo'] for key,arm in [('base','base'),('guard-stack','candidate')]):
        raise ValueError('self-trained PGO build audit does not match')
    stamps = {p:(p.stat().st_ino,p.stat().st_size,p.stat().st_mtime_ns) for pair in actual.values() for p in pair.values()}
    def select(arm):
        for role,dest in [('cargo',slot),('wild',linker)]:
            f = actual[arm][role]
            switch(f,dest)
            s = dest.stat()
            if (s.st_ino,s.st_size,s.st_mtime_ns) != stamps[f]:
                raise ValueError(f'changed {role} selection')
    edit = source/EDIT_PATH
    pristine = subprocess.check_output(['git','-C',str(WORK/'uv'),'show',f"{plan['uv']}:{EDIT_PATH}"])
    if edit.read_bytes() != pristine or pristine.count(BEFORE.encode()) != 1:
        raise ValueError('archived source is not pristine')
    initial_stat = edit.stat()
    home = Path(prior['cargo_home'])
    if not (home/'registry').is_dir() or home.stat().st_mode & 0o077:
        raise ValueError('invalid private Cargo home')
    env = dict(HOME=os.environ['HOME'], PATH=f"{sysroot}/bin:{os.environ['PATH']}", LANG='C.UTF-8', LC_ALL='C.UTF-8', TZ='UTC',
               CARGO_HOME=str(home), CARGO_TARGET_DIR=str(target), RUSTC=str(rustc), RUSTDOC=str(sysroot/'bin/rustdoc'),
               CARGO_NET_OFFLINE='true', CARGO_TERM_COLOR='never', SSL_CERT_DIR='/etc/ssl/certs')
    command = [str(slot), *plan['command']]
    def put(tag):
        after = ('{\n                component == cellar && (next == formula || next == OsStr::new('
                 f'"uv-preview-{tag}"))\n            }}')
        data = pristine.replace(BEFORE.encode(), after.encode())
        edit.write_bytes(data)
        return hashlib.sha256(data).hexdigest()
    def run(arm,label,*,trace=False,timed=False,fresh=False,allow_cold=False):
        select(arm)
        log = out/label
        log.mkdir()
        argv = (['strace','-ff','-qq','-v','-s','131072','-e','trace=execve,execveat','-o',str(log/'exec')] if trace else [])+command
        with (log/'cargo.log').open('x') as f:
            utc = time.time_ns() if timed else None
            start = time.perf_counter_ns() if timed else None
            proc = subprocess.Popen(argv,cwd=source,env=env,stdout=f,stderr=subprocess.STDOUT,start_new_session=True)
            rc = proc.wait()
            elapsed = time.perf_counter_ns()-start if timed else None
        # The default Wild can finish cleanup after Cargo exits. Keep that out of the next trial.
        limit = time.monotonic()+30
        while group := live_group(proc.pid):
            if time.monotonic() > limit:
                raise RuntimeError(f'live descendants after Cargo exit: {group}')
            time.sleep(.025)
        body = (log/'cargo.log').read_text(errors='replace')
        if rc or not re.search(r'^\s*Finished ',body,re.M) or re.search(r'^\s*(Running|Updating|Downloading|Blocking) |^running \d+ tests?',body,re.M):
            raise ValueError(f'{label}: failed, ran tests, accessed the network, or waited for a lock: {body[-500:]}')
        compiled = sorted(re.findall(r'^\s*(Checking|Compiling) (.+)$',body,re.M))
        tests = sorted(re.findall(r'^\s*Executable (.+)$',body,re.M))
        if len(tests) != 72 or len(set(tests)) != 72 or not any(t.startswith('tests/it/') for t in tests):
            raise ValueError(f'{label}: expected the 72 uv workspace test executables')
        if fresh and compiled:
            raise ValueError(f'{label}: predecessor is not fresh: {compiled}')
        if not allow_cold and not fresh and (len(compiled)!=1 or compiled[0][0]!='Compiling' or not compiled[0][1].startswith('uv v')):
            raise ValueError(f'{label}: unexpected compilation: {compiled}')
        roster = {'compiled': [list(x) for x in compiled], 'tests':tests}
        if trace:
            roster['roles'] = observe_exec(log,slot,rustc,linker)
        save(log/'receipt.json',dict(arm=arm, source_sha256=digest(edit), identities=identity[arm],
                                    command=command, roster=roster, elapsed_ns=elapsed, utc_ns=utc))
        return roster,elapsed,utc
    try:
        if a.phase == 'warm':
            info = dict(plan_sha256=digest(HERE/'plan.json'), command=command, source=str(source), target=str(target),
                        private_toolchain=str(sysroot), cargo_home=str(home), inputs=identity, rustc_sha256=elf(rustc),
                        original_cargo_sha256=elf(old['cargo']), original_private_wild_sha256=elf(old['wild']),
                        environment=env, original_seed=str(root/'seed-target'), common=str(scratch/'predecessor'),
                        predecessor_literal=cfg['prefix']+'00', admission_literal=cfg['prefix']+'01')
            save(out/'protocol.json',info)
            copy(root/'seed-target',target)
            try:
                run('base','warm',allow_cold=True)
                run('base','pristine-fresh',fresh=True)
                put(cfg['prefix']+'00')
                run('base','structural')
                run('base','structural-fresh',fresh=True)
            finally:
                target.rename(scratch/'predecessor')
            for arm in actual:
                copy(scratch/'predecessor',scratch/f'target-{arm}')
            copies = [snapshot(scratch/name) for name in ('predecessor','target-base','target-candidate')]
            if len({json.dumps(v,sort_keys=True) for v in copies}) != 1:
                raise ValueError('parked structural snapshots differ')
            put(cfg['prefix']+'01')
            rosters = []
            for arm in cfg['admission_order']:
                parked = scratch/f'target-{arm}'
                parked.rename(target)
                try:
                    rosters.append(run(arm,'admission-'+arm,trace=True)[0])
                finally:
                    target.rename(parked)
            if rosters[0] != rosters[1]:
                raise ValueError('native arm admission rosters differ')
            save(out/'READY.json',dict(plan_sha256=digest(HERE/'plan.json'),snapshot=copies[0],roster=rosters[0],identities=identity))
            print(f'{a.cohort}: same-state native admission passed',flush=True)
            return
        ready = json.loads((out/'READY.json').read_text())
        if ready['plan_sha256'] != digest(HERE/'plan.json') or ready['identities'] != identity:
            raise ValueError('registered plan or tool identities changed after admission')
        if a.phase == 'post-audit':
            if len(list(csv.DictReader((out/'pairs.csv').open()))) != 48:
                raise ValueError('post-audit requires the complete timing cohort')
            put(cfg['prefix']+'99')
            for arm in cfg['admission_order']:
                parked = scratch/f'target-{arm}'
                parked.rename(target)
                try:
                    work,_,_ = run(arm,'post-'+arm,trace=True)
                finally:
                    target.rename(parked)
                if work != ready['roster']:
                    raise ValueError(f'{arm} post-audit differed from native admission')
            save(out/'POST.json',{'matched':True})
            return
        expectation = {k:ready['roster'][k] for k in ('compiled','tests')}
        with (out/'pairs.csv').open('x',newline='') as f:
            writer = csv.DictWriter(f, ['pair','rank','arm','literal','source_sha256','elapsed_ns','utc_ns','cargo_sha256','wild_sha256'])
            writer.writeheader()
            f.flush()
            for idx,block in enumerate(cfg['schedule']):
                sha = put(block['literal'])
                for rank,arm in enumerate(block['arms']):
                    parked = scratch/f'target-{arm}'
                    parked.rename(target)
                    try:
                        work,t,utc = run(arm,f'pair-{idx:02}-{rank}-{arm}',timed=True)
                    finally:
                        target.rename(parked)
                    if work != expectation:
                        raise ValueError('timed package or test executable roster differed from admission')
                    writer.writerow(dict(pair=idx,rank=rank,arm=arm,literal=block['literal'],source_sha256=sha,elapsed_ns=t,utc_ns=utc,
                                         cargo_sha256=identity[arm]['cargo'],wild_sha256=identity[arm]['wild']))
                    f.flush()
                print(f'{a.cohort}: admitted native timing pair {idx+1}/24',flush=True)
    except Exception as err:
        save(out/f'FAILED-{a.phase}.json',{'reason':str(err)})
        raise
    finally:
        edit.write_bytes(pristine)
        os.utime(edit,ns=(initial_stat.st_atime_ns,initial_stat.st_mtime_ns))
        switch(old['cargo'],slot)
        switch(old['wild'],linker)
        if (any(elf(path)!=identity[arm][k] for arm,pair in actual.items() for k,path in pair.items())
                or elf(global_linker)!=plan['release_wild_sha256']):
            raise ValueError('an input or shared release linker changed during the cohort')
        lock.close()


if __name__ == '__main__':
    main()
