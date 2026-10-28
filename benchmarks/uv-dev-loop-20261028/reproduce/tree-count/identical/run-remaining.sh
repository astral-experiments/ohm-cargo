#!/bin/sh
set -u
here=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
for phase in pilot samples; do
    for ep in check build test; do
        result="$here/results/$ep"
        if [ "$phase" = pilot ] && { [ -f "$result/admission.json" ] || [ -f "$result/rejected-pilot.json" ]; }; then
            continue
        fi
        if [ "$phase" = samples ] && { [ ! -f "$result/admission.json" ] || [ -f "$result/samples.csv" ]; }; then
            continue
        fi
        log="$here/driver-$phase-$ep.log"
        if [ -e "$log" ]; then
            printf 'Refusing to overwrite %s\n' "$log" >&2
            exit 2
        fi
        printf 'Starting %s %s\n' "$phase" "$ep"
        taskset -c 16-23 /usr/bin/python3 -B "$here/../identical.py" "$phase" "$ep" >"$log" 2>&1
        result_code=$?
        cat "$log"
        printf 'Finished %s %s with status %s\n' "$phase" "$ep" "$result_code"
        if [ "$result_code" -ne 0 ] && [ ! -f "$result/rejected-$phase.json" ]; then
            printf 'Infrastructure failure before an endpoint admission decision; stopping\n' >&2
            exit "$result_code"
        fi
    done
done
/usr/bin/python3 -B "$here/summarize.py"
