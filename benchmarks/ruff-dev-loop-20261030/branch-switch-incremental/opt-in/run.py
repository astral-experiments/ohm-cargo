"""Run the measured history-selection replay with one installed compiler."""
from pathlib import Path
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile


def digest(path):
    with path.open("rb") as file:
        return hashlib.file_digest(file, "sha256").hexdigest()


def main():
    here = Path(__file__).resolve().parent
    benchmark = here.parent
    sources = json.loads((here / "replay-sources.json").read_bytes())
    origins = {
        "replay.py": benchmark / "replay.py",
        "compiler_counts.py": benchmark / "compiler_counts.py",
        "consumer.rs": benchmark / "consumer.rs",
        "trace-compilers.c": benchmark / "trace-compilers.c",
        "count.py": benchmark / "storage" / "count.py",
    }
    with tempfile.TemporaryDirectory(prefix="ohm-branch-replay-") as temp:
        target = Path(temp)
        for name, src in origins.items():
            if digest(src) != sources["inputs"][name]:
                raise ValueError(f"Unexpected source for {name}")
            shutil.copyfile(src, target / name)
        diff = here / "replay.diff"
        if digest(diff) != sources["patch"]:
            raise ValueError("Unexpected replay patch")
        subprocess.run(["patch", "--batch", "--forward", "--quiet", "-p0", "-i", diff],
                       cwd=target, check=True)
        if digest(target / "replay.py") != sources["measured_replay"]:
            raise ValueError("The rebuilt replay differs from the measured runner")
        args = sys.argv[1:]
        if args[:1] == ["--screen"]:
            diff = here / "screen.diff"
            if digest(diff) != sources["screen_patch"]:
                raise ValueError("Unexpected screen patch")
            subprocess.run(["patch", "--batch", "--forward", "--quiet", "-p0", "-i", diff],
                           cwd=target, check=True)
            if digest(target / "replay.py") != sources["screen_replay"]:
                raise ValueError("The rebuilt replay differs from the screened runner")
            args = args[1:]
        subprocess.run([sys.executable, "-IB", target / "replay.py", *args], check=True)


if __name__ == "__main__":
    main()
