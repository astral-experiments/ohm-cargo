"""Run the registered V4 vs V3 full native Cargo series with an independent audit."""
import json
import os
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))
from paired import Study, getargs, log_json, sha

HERE = Path(__file__).resolve().parent
PLAN = HERE / 'screen4-registration.json'
PLAN_SHA = '03a651402afa58a11a4ff9fc952c486cb2f4b32088b3d546a054a00df284743f'
ROOTS = {'hold_direct', 'hold_indirect', 'hold_plain'}
READERS = {'hold_direct', 'hold_bridge'}
FULL = READERS | {'hold_indirect', 'hold_shapes'}


def verify_row(row, reference, *, audit=False, edit=False):
    assert row['status'] == 0 and row['timed'] != audit, row['phase']
    assert row['source'] == reference['source']
    assert set(row['native_products']) == ROOTS
    assert row['native_products'] == reference['native_products'], row['phase']
    assert len(row['readers']) == 2
    assert all(x['signed'] and x['complete'] for x in row['readers'].values())
    if audit:
        roster = row['roster']
        assert len(roster) == (5 if edit else 0), (row['phase'], roster)
        assert {x['crate'] for x in roster if x['mode'] == 'full'} == (FULL if edit else set())
        assert {x['crate'] for x in roster if x['mode'] == 'relink'} == ({'hold_plain'} if edit else set())
        assert {x['crate'] for x in roster if x['capture']} == (READERS if edit else set())
        assert all(x['checksum'] for x in roster if x['capture'])


def main():
    study = Study(getargs())
    v3 = Path(os.environ['PREVIOUS_CARGO']).resolve()
    study.bins['V'] = v3
    frozen = json.loads(PLAN.read_text())
    assert sha(PLAN) == PLAN_SHA and study.a.cpus == '0-3'
    subject = frozen['subject']
    assert sha(v3) == subject['V']['cargo_sha256']
    assert study.digest['C'] == subject['C']['cargo_sha256']
    assert study.digest['P'] == subject['golden_Cargo_sha256']
    assert study.digest['rustc'] == subject['frontend_sha256']
    assert study.digest['driver'] == subject['compiler_driver_sha256']
    assert sha(HERE / 'observer-edit-screen1.patch') == subject['C']['patch_sha256']
    metadata = json.loads((study.logs / 'subject.json').read_text())
    metadata['plan'] = PLAN_SHA
    metadata['sha256']['V'] = sha(v3)
    metadata['resolved']['V'] = str(v3)
    metadata['subject'] = subject
    log_json(study.logs / 'subject.json', metadata)
    study.references()
    for tag in ('native', 'audit'):
        trace = tag == 'audit'
        arms = {arm: study.init(tag + '-store-' + arm) for arm in ('V', 'C')}
        for arm, store in arms.items():
            for phase in range(4):
                row = study.run(store, arm, f'{tag}-training-{arm}-{phase}', trace=True)
                study.equivalent(row, study.gold[False])
            verify_row(row, study.gold[False], audit=True)
        for block in frozen['orders']:
            for phase in ('noop', 'edit'):
                edit = phase == 'edit'
                new = (block['edited_state'] == 'add') == edit
                for arm in block[phase]:
                    if edit:
                        study.edit(arms[arm], new)
                    row = study.run(arms[arm], arm, f"{tag}-{block['block']:02}-{phase}-{arm}", trace=trace)
                    verify_row(row, study.gold[new], audit=trace, edit=edit)
    assert len(study.results) == 114
    log_json(study.logs / 'passes.json', {'observations': len(study.results), 'selected': 96,
                                         'native_and_audit_agree_with_empty': True})


if __name__ == '__main__':
    main()
