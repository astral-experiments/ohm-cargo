"""Untimed input-read attribution. The live pipe writes only aggregate byte counts to disk."""

from pathlib import Path
import json
import shlex
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import reproduce


def main():
    s = reproduce.Study(reproduce.getargs())
    s.references()
    arms = {arm: s.init("diagnose-" + arm) for arm in "PC"}
    s.train(arms, "train")
    original = subprocess.run

    def runner(cmd, *args, **kwargs):
        command = list(cmd)
        if "strace" in command:
            trace_index = command.index("strace")
            out = Path(command[command.index("-o") + 1])
            output = out.parent / "read-activity.csv"
            out.touch(exist_ok=False)
            # strace sends the data to a child process, never to the workspace's exec file.
            command[command.index("-o") + 1] = "|" + shlex.join(
                [
                    sys.executable,
                    "-EB",
                    str(Path(__file__).with_name("aggregate_reads.py").resolve()),
                    str(output),
                ]
            )
            command[command.index("trace=execve")] = "trace=execve,read,pread64,clone,clone3,fork,vfork"
            command[command.index("-s") + 1] = "350"
            command.insert(trace_index + 1, "-y")
        return original(command, *args, **kwargs)

    subprocess.run = runner
    try:
        for phase, edited in [("steady", False), ("first-edit", True), ("back-edit", False)]:
            for arm, store in arms.items():
                if phase != "steady":
                    s.edit(store, edited)
                result = s.run(store, arm, phase + "-" + arm, trace=True)
                s.equivalent(result, s.gold[edited])
                output = s.logs / result["phase"] / "read-activity.csv"
                # This cost-only trace has no exported executable-event roster.
                result.pop("roster", None)
                result.pop("successful_exec_images", None)
                result["read_counts"] = "read-activity.csv"
                (output.parent / "result.json").write_text(
                    json.dumps(result, indent=2, sort_keys=True) + "\n"
                )
                if output.stat().st_size < 60:
                    raise RuntimeError("missing streamed read attribution")
    finally:
        subprocess.run = original


if __name__ == "__main__":
    main()
