# Exact function bodies from the existing frozen paired.py.
# Origin SHA256: 50d0cb2d4f595ccfa72d463fedb3ff4dadf9dfc1446c749d482d9ede8418c7cf
import os
import resource
import shutil
import subprocess
import time

def run_command(command, cwd, environment, stdout_path, stderr_path):
    before = resource.getrusage(resource.RUSAGE_CHILDREN)
    with stdout_path.open("wb") as stdout, stderr_path.open("wb") as stderr:
        started = time.perf_counter_ns()
        process = subprocess.run(command, cwd=cwd, env=environment, stdout=stdout, stderr=stderr)
        elapsed_ns = time.perf_counter_ns() - started
    after = resource.getrusage(resource.RUSAGE_CHILDREN)
    return {
        "returncode": process.returncode,
        "wall_ns": elapsed_ns,
        "user_seconds": after.ru_utime - before.ru_utime,
        "system_seconds": after.ru_stime - before.ru_stime,
        "minor_faults": after.ru_minflt - before.ru_minflt,
        "major_faults": after.ru_majflt - before.ru_majflt,
        "voluntary_context_switches": after.ru_nvcsw - before.ru_nvcsw,
        "involuntary_context_switches": after.ru_nivcsw - before.ru_nivcsw,
        "stdout": str(stdout_path),
        "stderr": str(stderr_path),
    }

def install_variant(source, destination):
    """Replace a regular file atomically, never overwrite a symlink's target."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.is_symlink():
        raise ValueError(f"canonical executable must be a regular file, not a symlink: {destination}")
    temporary = destination.with_name(destination.name + ".bench-tmp")
    shutil.copyfile(source, temporary)
    os.chmod(temporary, source.stat().st_mode & 0o777)
    temporary.replace(destination)
