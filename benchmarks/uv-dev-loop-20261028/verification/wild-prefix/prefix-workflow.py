"""Generate the exact-source linker validation from the already verified native workflow."""
import argparse
from pathlib import Path
import re


here = Path(__file__).resolve().parent
cli = argparse.ArgumentParser(description=__doc__)
cli.add_argument('head')
cli.add_argument('pr', type=int)
cli.add_argument('output', type=Path)
args = cli.parse_args()
if not re.fullmatch('[0-9a-f]{40}', args.head):
    cli.error('a full Git commit is required')
parent = 'a77381c04eb7ad9258cdd0475642815a2a1da711'
release = 'e856d81f6683cad80b9fe0ebf1a0c3c403c6fe11'
workflow = (here / 'native-ci-v2.yml').read_text()


def replace(old, new, expected=1):
    global workflow
    assert workflow.count(old) == expected, old
    workflow = workflow.replace(old, new)


replace(parent, args.head, 3)
replace(release, parent)
replace('Wild 0.11 native linker validation', 'Wild ELF section placement validation')
replace('exact #45 source', f'exact #{args.pr} source')
replace('Compare AArch64 lit fixtures against 0.11.0', 'Compare AArch64 lit fixtures against the parent')
replace('groups=(undefined-symbol:1 dylib-undefined:1 common-weak:2)',
        'groups=(section-identity:1 empty-section:1 data-const-no-got:1 arbitrary-segments:1)')
replace('groups=(undefined-symbols:5 multiple-undefined-symbols:1 undefined-weak-and-strong:1 comdat-undefined:1 shlib-undefined:4)',
        '''groups=(custom-section:2 exclude-section:1 linker-script-discard:1 linker-script-filename-match:1 linker-script-short-section-name:1 orphan-handling:26 partial-link-repeated-sections:1 sort-section-name:1 sort-section-alignments:1)
            unitlog=$(mktemp)
            cargo test --locked --profile ci -p libwild --lib -- elf::test_default_section_name_prefixes --exact --color never | tee "$unitlog"
            grep -F 'test result: ok. 1 passed; 0 failed; 0 ignored;' "$unitlog"
            mkdir -p "$RUNNER_TEMP/no-cet"
            printf '%s\\n' '#!/usr/bin/env bash' 'exec /usr/bin/gcc -fcf-protection=none "$@"' > "$RUNNER_TEMP/no-cet/gcc"
            chmod +x "$RUNNER_TEMP/no-cet/gcc"
            ln -s gcc "$RUNNER_TEMP/no-cet/cc"''')
replace('            cargo test --locked --profile ci -p wild-linker',
        '''            fixture_env=()
            if [[ "$name" == orphan-handling ]]; then
              fixture_env+=("PATH=$RUNNER_TEMP/no-cet:$PATH" "WILD_TEST_BUILD_DIR=$RUNNER_TEMP/orphan-fixtures")
            fi
            env "${fixture_env[@]}" cargo test --locked --profile ci -p wild-linker''')
args.output.write_text(workflow)
