#!/bin/sh
set -eu
src=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
work=$(mktemp -d "${TMPDIR:-/tmp}/ohm-native-macro-XXXXXX")
printf 'Work directory: %s\n' "$work"
cp "$src/native.rs" "$src/reader.rs" "$work"
cd "$work"
for value in 17 29; do
    printf 'int value(void) { return %s; }\n' "$value" > value.c
    cc -fPIC -c value.c -o value.o
    rustc +ohm native.rs -Clink-arg=value.o
    rustc +ohm reader.rs --extern native=libnative.so -Zcache-proc-macros -C incremental=warm -o reader
    warm=$(./reader)
    rustc +ohm reader.rs --extern native=libnative.so -Zcache-proc-macros -C incremental="empty-$value" -o empty
    clean=$(./empty)
    printf 'C returned %s, warm reader %s, empty reader %s\n' "$value" "$warm" "$clean"
    test "$clean" = "$value,$value"
    test "$warm" = "$clean"
done
