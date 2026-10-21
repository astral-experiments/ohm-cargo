"""Reject compiler/profiler activity and sustained controllers, including gaps."""
import os
from pathlib import Path
import subprocess

BUILDERS = {'cargo', 'rustc', 'rustdoc', 'rust-lld', 'ld.lld', 'ld', 'cc', 'cc1', 'cc1plus',
            'clang', 'clang++', 'gcc', 'g++', 'collect2', 'ninja', 'make', 'cmake', 'valgrind',
            'perf', 'hyperfine', 'cargo-nextest'}
CONTROLLERS = {'paired.py', 'paired_repeated.py', 'loader_fixture.py', 'measure.py',
               'native_controller.py', 'native_controller-v2.py', 'native_controller-v3.py',
               'native_controller-v4.py', 'native_driver.py',
               'driver.py', 'run_restacked_ir.py', 'launch-linux.py', 'run-suite.py'}


def require_quiet():
    probe = subprocess.Popen(['ps', '-eo', 'pid=,pcpu=,pmem=,comm=', '--sort=-pcpu'],
                             stdout=subprocess.PIPE, text=True)
    output, _ = probe.communicate()
    assert probe.returncode == 0
    ignored = {os.getpid(), probe.pid}
    competing = []
    rows = output.splitlines()
    for row in rows:
        pid, cpu, _memory, name = row.split(None, 3)
        pid, cpu, name = int(pid), float(cpu), name.strip()
        if pid in ignored:
            continue
        try:
            argv = [os.fsdecode(part) for part in Path(f'/proc/{pid}/cmdline').read_bytes().split(b'\0') if part]
        except (OSError, PermissionError):
            argv = []
        scripts = [Path(arg).name for arg in argv if arg.endswith('.py')]
        controller = any(script in CONTROLLERS or script.startswith('build_driver_') for script in scripts)
        if name in BUILDERS or name.startswith(('cargo-', 'callgrind-', 'cachegrind-', 'build-script', 'testsuite-')) or cpu >= 50 or controller:
            competing.append({'pid': pid, 'name': name, 'cpu_percent': cpu, 'controller': controller, 'argv': argv})
    assert not competing, competing
    return {'process_snapshot': rows[:20], 'load_average': list(os.getloadavg()), 'other_workloads': competing}
