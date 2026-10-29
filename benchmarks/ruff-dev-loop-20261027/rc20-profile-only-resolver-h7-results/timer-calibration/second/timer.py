"""A blocking child exit is the normal observation. Arm and disarm the independent watchdog outside it."""
import signal
import subprocess
import time

def expired(signum, frame):
    raise TimeoutError('independent child deadline expired')

def capture(cmd, cwd, env, so, se, deadline_seconds=120):
    original = signal.signal(signal.SIGALRM, expired)
    assert signal.getitimer(signal.ITIMER_REAL) == (0.0, 0.0)
    child = None
    try:
        signal.setitimer(signal.ITIMER_REAL, deadline_seconds)
        before = time.perf_counter_ns()
        child = subprocess.Popen(cmd, cwd=cwd, env=env, stdout=so, stderr=se)
        code = child.wait()
        after = time.perf_counter_ns()
        return code, before, after
    except BaseException:
        if child is not None:
            child.kill()
            child.wait()
        raise
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, original)
