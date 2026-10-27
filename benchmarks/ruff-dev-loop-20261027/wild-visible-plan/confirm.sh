#!/usr/bin/env bash
set -euo pipefail
root=/mnt/devbox-scratch/dev-user/ohm-whole-skips-20261027
cd "$root/wild-package-v8"
exec >launch.log 2>&1
trap 'echo "$?" >launch.rc' EXIT
printf '%s  %s\n' c813de15da27872ce0a294a321053674fa8e7c08b4443798b831a6da5d37374c candidate-wild | sha256sum -c -
printf '%s  %s\n' 2a6a045a42706dd59a332c2e6a910ee8771c7b55f5b303c041c0ca6bec4378e0 edit.patch | sha256sum -c -
while tmux has-session -t ohm-wild-v7-1027 2>/dev/null; do sleep 30; done
test -e ../wild-package-v7/launch.rc
common=(--candidate ../subjects/parent --parent-wild ../wild-package-v7/parent-wild
        --candidate-wild candidate-wild --wild-observe --queue --no-new-registries)
for mode in build test; do
    seed=1738071
    if [[ $mode == test ]]; then seed=1738072; fi
    python3 triple-native.py "wild-package-v8-ide-$mode" "$mode" ../wild-assets/patches/ide-unit-test.patch \
        "${common[@]}" --shipped-wild ../wild-package-v7/shipping-wild --seed "$seed" \
        --reuse-completed-targets "wild-package-v7-ide-$mode" >"ide-$mode.log" 2>&1
done
python3 triple-native.py wild-package-v8-snapshot-test test edit.patch "${common[@]}" \
    --shipped-wild ../wild-package-v7/shipping-wild --seed 1738073 \
    --reuse-completed-targets wild-package-v8-ide-test >snapshot.log 2>&1
python3 analyze-triple.py ../results-wild-package-v8-{ide-build,ide-test,snapshot-test} >statistics.json
if [[ ! -e ../results-wild-package-v7-miss-build/complete.json ]]; then
    test ! -e ../results-wild-package-v7-miss-build
    (cd ../wild-package-v7; python3 paired-native.py wild-package-v7-miss-build build ../wild-assets/patches/pydantic.patch \
        --candidate ../subjects/parent --parent-wild parent-wild --candidate-wild candidate-wild --wild-observe \
        --no-new-registries --queue --seed 1729073 >miss-recovery.log 2>&1)
fi
python3 paired-native.py wild-package-v8-miss-build build ../wild-assets/patches/pydantic.patch \
    "${common[@]}" --seed 1738074 --reuse-completed-targets wild-package-v7-miss-build >miss.log 2>&1
python3 analyze-native.py ../results-wild-package-v8-miss-build >miss-statistics.json
