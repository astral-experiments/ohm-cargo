#!/bin/sh
set -eu
here=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
work=$(dirname -- "$here")
[ "${1:-}" = --coordinator-released ] || { echo 'Wait for the coordinator to release the quiet host.' >&2; exit 2; }
for cohort in initial replica; do
    test -f "$here/results/$cohort/READY.json"
    test ! -e "$here/results/$cohort/pairs.csv"
done
exec 8>"$work/native-wall-measurement.lock"
flock -n -x 8 || { echo 'The native measurement lock is occupied.' >&2; exit 1; }
export OHM_EIGHT_NATIVE_RELEASED=yes
native=$(/usr/bin/python3 -B -c 'import json,sys; print(",".join(map(str,json.load(open(sys.argv[1]))["native_cpus"])))' "$here/plan.json")
monitor_cpu=${OHM_EIGHT_MONITOR_CPU:-31}
for cohort in initial replica; do
    taskset -c "$monitor_cpu" /usr/bin/python3 -B "$here/quiet.py" "$cohort"
    taskset -c "$monitor_cpu" /usr/bin/python3 -B "$here/quiet.py" "$cohort" --observe &
    monitor=$!
    trap 'kill "$monitor" 2>/dev/null || true' EXIT
    taskset -c "$native" /usr/bin/python3 -B "$here/run.py" measure "$cohort"
    kill "$monitor"
    wait "$monitor" || true
    trap - EXIT
done
for cohort in initial replica; do
    taskset -c "$native" /usr/bin/python3 -B "$here/run.py" post-audit "$cohort"
done
/usr/bin/python3 -B "$here/summarize.py"
