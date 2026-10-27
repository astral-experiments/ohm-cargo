#!/usr/bin/env bash
set -euo pipefail
root=/mnt/devbox-scratch/dev-user/ohm-whole-skips-20261027
cd "$root/wild-package-v7"
exec >launch.log 2>&1
trap 'printf "%s\n" "$?" >launch.rc' EXIT
printf '%s  %s\n' 560f5a182eae3cd598b1b0a97a878308e1890ce46ab0b70aa32670586388fbb4 candidate-wild | sha256sum -c -
common=(--candidate ../subjects/parent --parent-wild parent-wild --candidate-wild candidate-wild --wild-observe --queue --no-new-registries)
for mode in build test; do
    seed=1729071
    if [[ $mode == test ]]; then seed=1729072; fi
    python3 triple-native.py "wild-package-v7-ide-$mode" "$mode" ../wild-assets/patches/ide-unit-test.patch \
        "${common[@]}" --shipped-wild shipping-wild --seed "$seed" >"$mode.log" 2>&1
done
python3 analyze-triple.py ../results-wild-package-v7-ide-build ../results-wild-package-v7-ide-test >primary-statistics.json
python3 paired-native.py wild-package-v7-miss-build build ../wild-assets/patches/pydantic.patch \
    "${common[@]}" --seed 1729073 >miss.log 2>&1
python3 paired-native.py wild-package-v7-comment-build build ../wild-assets/patches/semantic-comment.patch \
    "${common[@]}" --seed 1729074 --pilot >comment.log 2>&1
