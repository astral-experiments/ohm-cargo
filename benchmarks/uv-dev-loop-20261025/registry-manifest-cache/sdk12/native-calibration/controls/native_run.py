"""One unwrapped Cargo process; raw completion precedes any output validation."""
import os
import signal
import subprocess
import time
import common as C


def run(log, label, descendants, *, timed, trace=False):
    assert not (timed and trace)
    command = C.PROTOCOL['command'][:]
    if trace:
        command = [str(C.ROOT/'aux/strace-capture'), '-f', '-qq', '--seccomp-bpf', '-v', '-s', '65536',
                   '-e', 'trace=execve,execveat', '-o', str(log/(label+'.trace'))] + command
    C.save(log/(label+'.command.json'), {'argv': command, 'cwd': str(C.ROOT/'uv'),
           'environment': C.ENV, 'source_sha256': C.sha(C.SOURCE), 'workload_cpus': list(range(8)),
           'cargo_sha256': C.sha(C.ROOT/'bin/cargo'), 'timed': timed, 'trace': trace,
           'tests_executed': False, 'timer_unit': 'nanoseconds' if timed else None})
    def timeout(sig, frame):
        raise TimeoutError('native command exceeded 300 seconds')
    signal.signal(signal.SIGALRM, timeout)
    proc = None
    elapsed = None
    failure = None
    try:
        with (log/(label+'.stdout')).open('xb') as out, (log/(label+'.stderr')).open('xb') as err:
            # Same Popen/wait boundaries as the accepted K/W native controls.
            start = time.perf_counter_ns()
            proc = subprocess.Popen(command, cwd=C.ROOT/'uv', env=C.ENV, stdin=subprocess.DEVNULL,
                                    stdout=out, stderr=err, start_new_session=True, umask=0o077,
                                    preexec_fn=lambda: os.sched_setaffinity(0, range(8)))
            signal.alarm(300)
            code = proc.wait()
            elapsed = time.perf_counter_ns() - start
    except BaseException as error:
        failure = {'type': type(error).__name__, 'message': str(error)}
        if proc is not None:
            descendants.groups.add(proc.pid)
            descendants.terminate_owned(label+'-abort', primary=proc)
        raise
    finally:
        signal.alarm(0)
        if proc is not None:
            descendants.groups.add(proc.pid)
        # The raw process outcome is durable even if a later decoder/guard fails.
        C.save(log/(label+'.exit.json'), {'returncode': None if proc is None else proc.returncode,
               'pid': None if proc is None else proc.pid, 'new_session': True, 'failure': failure})
        if timed and elapsed is not None:
            C.save(log/(label+'.elapsed.json'), {'unit': 'nanoseconds', 'elapsed_ns': elapsed})
    assert code == 0, 'Cargo returned nonzero; raw stdout/stderr retained'
    return proc.pid
