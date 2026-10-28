#!/bin/bash
set -u
d=/mnt/devbox-scratch/dev-user/ohm-observer-shipping-20261027
p=$d/gates-v4; cd "$p/input" || exit 1
v=$1; export PATH=/home/dev-user/.cargo/bin:$PATH
case "$v" in
 rc17) export QUALIFIED_CARGO=$d/subjects/rc17-complete-v4 QUALIFIED_RELEASE=$d/assets/raw-rc17-unicode-fixed QUALIFIED_OLD_CARGO=$d/subjects/rc17-control QUALIFIED_OLD_RELEASE=$d/assets/raw-rc17-final-control;;
 r16) export QUALIFIED_CARGO=$d/subjects/raw-complete-v4 QUALIFIED_RELEASE=$d/assets/raw-r16-unicode-fixed; unset QUALIFIED_OLD_CARGO QUALIFIED_OLD_RELEASE;;
 *) exit 2;;
esac
o=$p/$v; mkdir "$o" || exit 2; mkdir "$o/cmd" || exit 1; failures=0
run() {
 label=$1; shift
 printf '%q ' "$@" >"$o/cmd/$label.argv"; printf '\n' >>"$o/cmd/$label.argv"
 taskset -c 8-11 "$@" >"$o/cmd/$label.log" 2>&1
 rc=$?; echo "$rc" >"$o/cmd/$label.rc"; if test "$rc" -ne 0; then echo "FAIL $label $rc"; failures=$((failures+1)); else echo "PASS $label"; fi
}
test -f "$QUALIFIED_RELEASE/sdk.json" || exit 1
run source-positive python3 -B complete-rmake-lossy.py "$o/source-positive" --sdk "$QUALIFIED_RELEASE/toolchain" --expect success
old=$d/assets/stock16-sdk; test "$v" != rc17 || old="$QUALIFIED_OLD_RELEASE/toolchain"
run source-negative python3 -B complete-rmake-lossy.py "$o/source-negative" --sdk "$old" --expect failure
run true-fifo python3 -B tracked-special.py "$o/true-fifo" --sdk "$QUALIFIED_RELEASE/toolchain"
run alias env QUALIFIED_SDK="$QUALIFIED_RELEASE/toolchain" python3 -B raw-final-alias-retarget.py "$o/alias"
for arg in fixed:fixed old:fixed fixed:old old:old upgrade:old downgrade:fixed; do c=${arg%:*}; z=${arg#*:}
 run "build-$c-$z" python3 -B complete-matrix-final.py "$o/build-$c-$z" --cargo "$c" --rust "$z"
 if test "$c" != downgrade; then run "check-$c-$z" python3 -B complete-check-final.py "$o/check-$c-$z" --cargo "$c" --rust "$z"; fi
done
run escaped-fifo env RUSTUP_HOME="$o/build-fixed-fixed/rustup" python3 -B fifo-decoy.py "$o/escaped-fifo" --expect fixed
for arg in fixed:fixed old:fixed fixed:old old:old upgrade:old; do c=${arg%:*}; z=${arg#*:}; run "unicode-check-$c-$z" env ONLY_CHECK=1 python3 -B lossy-cargo-v3.py "$o/unicode-check-$c-$z" --cargo "$c" --rust "$z"; done
if test "$v" = rc17; then
 run unicode-check-from-prototype env ONLY_CHECK=1 QUALIFIED_OLD_CARGO="$d/subjects/rc17-complete-v3" QUALIFIED_OLD_RELEASE="$d/assets/raw-rc17-final-fixed" python3 -B lossy-cargo-v3.py "$o/unicode-check-from-prototype" --cargo upgrade --rust old
fi
echo "$failures" >"$o/suite.failures"; date -u >"$o/complete"; exit "$failures"
