"""Recheck the projected Cargo, compiler, linker, process and file evidence."""
import argparse
from collections import Counter
from copy import deepcopy
import gzip
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(name):
    with gzip.open(ROOT / name, 'rt') as f:
        return json.load(f)


def check(ruff, switches, direct, files):
    tags = ['cold-original', 'original-repeat', 'edited', 'edited-repeat', 'invalid', 'restored', 'restored-repeat', 'clean-edited', 'clean-invalid']
    assert [r['phase'] for r in ruff] == tags
    rs = {r['phase']: r for r in ruff}
    origin = rs['cold-original']['public_elf']
    edited = rs['edited']['public_elf']
    assert origin == [151043112,'8b1a5a8891f967496460d7265650454cd733b72215c827629561295e6956e97f']
    assert edited == [151042424,'654c387f46038be7c1e0dae45d489787bb9f5e5fe9422ea9070d88f1529dff46']
    for r in ruff:
        phase = r['phase']
        invalid = phase.endswith('invalid')
        success = not invalid
        assert r['cargo_json_success'] == success and r['cargo_exit'] == (0 if success else 101)
        assert len(r['artifacts']) == (373 if success else 372)
        dirty = [a for a in r['artifacts'] if not a['fresh']]
        cold = phase in ('cold-original','clean-edited')
        assert len(dirty) == (373 if cold else int(phase in ('edited','restored')))
        if len(dirty) == 1:
            assert dirty[0]['target'] == 'ruff' and dirty[0]['kind'] == ['bin']
        assert r['job_traced'] == (not cold)
        actual = Counter(e['tool'] for e in r['real_exec'])
        expect = {'rustc': 1} if invalid else {k: 1 for k in ('rustc','cc','collect2','bundled-wild')} if phase in ('edited','restored') else {}
        assert actual == expect
        for e in r['real_exec']:
            if e['tool'] == 'rustc':
                assert e['crate'] == 'ruff' and e['consumer_mode'] == 'full' and e['emit_recipe'] and e['persistent_temp_option'] and e['root_extern_count'] == 100
        if invalid:
            assert 'E0308' in r['diagnostics'] and not r['cli']
        else:
            assert [v['name'] for v in r['cli']] == ['response','working']
            edited_source = phase in ('edited','edited-repeat','clean-edited')
            assert [(v['exit'],v['error_class']) for v in r['cli']] == [(101,'missing-file-panic') if edited_source else (2,'graceful-missing-response'),(0,'none')]
            assert r['cli'][1]['stdout'] == 'x = 1\n'
    assert all(rs[i]['public_elf'] == origin for i in ('original-repeat','restored','restored-repeat'))
    assert all(rs[i]['public_elf'] == edited for i in ('edited-repeat','invalid'))
    assert rs['clean-edited']['public_elf'] == rs['clean-invalid']['public_elf'] != edited
    assert set(rs['edited']['artifacts'][0]) == {'package','target','kind','features','fresh'}
    assert len(switches) == 28
    for subject in ('pr284','published19'):
        group = [row for row in switches if row['product'] == subject]
        for first in ('default','no'):
            s = [row for row in group if row['first'] == first]
            assert [r['phase'] for r in s] == ['initial','initial-repeat','switch','switch-repeat','edit','restore','restore-repeat']
            other = 'no' if first == 'default' else 'default'
            assert [r['mode'] for r in s] == [first,first,other,other,other,other,other]
            baseline,clean_other = (17,29) if first == 'default' else (29,17)
            assert [int(r['value']) for r in s] == [baseline]*4 + [clean_other]*3
            assert [r['dirty'] for r in s] == [['origin','facade','probe'],[],[],[],['probe'],['probe'],[]]
            assert len({s[i]['elf'] for i in range(4)}) == 1
            for i,r in enumerate(s):
                counts = Counter(n['tool'] for n in r['real_exec'])
                assert counts['rustc-probe'] == int(i in (0,4,5))
                assert counts['bundled-wild'] == (2 if i == 0 else int(i in (4,5)))
                assert [name for name,fresh in r['typed_units'] if not fresh] == r['dirty']
                for n in r['real_exec']:
                    if n['tool'] == 'rustc-probe':
                        assert n['recipe'] == n['persistent_temp_option'] == (r['mode'] == 'default')
    assert len(direct) == 6
    for crate in ('probe','ruff'):
        a,b,c = [r for r in direct if r['crate'] == crate]
        assert [row['mode'] for row in [a,b,c]] == ['original-A','no-recipe-B','original-A2']
        assert a['raw_source_command'] == b['raw_source_command'] == c['raw_source_command'] == a['observed_rustc'] == c['observed_rustc']
        assert b['observed_rustc'] != a['observed_rustc'] and b['observed_rustc'] == a['remove_only_emit_from_original']
        assert a['native']['rustc']['argc'] == c['native']['rustc']['argc'] == b['native']['rustc']['argc'] + 2
        assert a['recipe'] and c['recipe'] and not b['recipe'] and a['object_sizes'] and not b['object_sizes']
        for row in (a,b,c):
            assert set(row['native']) == {'rustc','cc','collect2','ld.bfd'} and row['proxy_exec_is_separate']
            assert row['kept_temps_dir'] and row['all_cgu_under_original_dir'] and row['cgu_arg_count'] == (22 if crate == 'ruff' else 7)
            assert len(row['positive_prot_exec_mmap_wires']) == (23 if crate == 'ruff' else 1)
            assert all(v for v in row['positive_prot_exec_mmap_wires'].values())
            assert row['cpus'] == [14]
        for row in (b,c):
            assert Counter(v['kind'] for v in row['stock_argv_diff_from_A']) == {'CGU': a['cgu_arg_count'],'GCC resolution':1,'symbols.o':1,'raw-dylibs':1}
        if crate == 'ruff':
            assert a['elf'] == b['elf'] == c['elf'] == origin
            assert a['verdicts'] == b['verdicts'] == c['verdicts']
            for n in ('clap_derive','serde_derive','ruff_macros'):
                assert any(s.startswith('lib'+n+'-') for s in a['positive_prot_exec_mmap_wires'])
        else:
            assert a['elf'] == c['elf'] != b['elf'] and a['elf'][0] == b['elf'][0]
            assert [r['verdicts'][0]['stdout'] for r in (a,b,c)] == ['17\n','29\n','17\n']
    objs = files['objects']; assert len(objs) == files['record']['listed_objects'] == 22
    assert sum(r['bytes'] for r in objs) == 294952 and sum(r['bytes'] for r in objs if r['links'] == 1) == 1048
    assert sum(r['same_inode_in_incremental_store'] == 1 and r['links'] == 2 for r in objs) == 21
    assert files['recipe']['size'] == 127635 and files['record']['size'] == 7400 and files['record']['unused'] is None and not files['record']['unused_field_present']
    assert files['elf']['public'] == files['elf']['sha'] == origin[1] and files['elf_matches']
    assert len(files['externs']) == 100 and len(files['proc_macro_artifacts']) == 28 and 'clap' in files['externs'] and 'serde' in files['externs']


def main():
    p = argparse.ArgumentParser(description=__doc__); p.add_argument('--self-test',action='store_true');args = p.parse_args()
    for ln in (ROOT/'SHA256SUMS').read_text().splitlines():
        val, rel = ln.split('  ',1); assert digest(ROOT/rel) == val, rel
    r = load('ruff.json.gz'); s = load('switches.json.gz'); d = load('direct.json.gz'); f = json.loads((ROOT/'retained-files.json').read_bytes()); check(r,s,d,f)
    repeat = json.loads((ROOT/'reproducer-verdicts.json').read_bytes()); assert repeat['cargo'] == '789c2f116732ed642565d0f92c500838f8cd53664fbe60f205a5621c43cbecf1'
    assert [(row['from'],row['phase'],row['value'],row['dirty']) for row in repeat['rows']] == [(row['first'],row['phase'],int(row['value']),row['dirty']) for row in s if row['product'] == 'published19']
    survey = load('tip-audit.json.gz'); assert (survey['named_branches'],survey['all_state_prs'],len(survey['tips']),len(survey['blobs'])) == (293,237,297,109)
    assert sum(bool(t['modules']) for t in survey['tips'].values()) == 284 and all(t['modules'] or t['has_evidence_only_name'] for t in survey['tips'].values())
    assert sorted(i for t in survey['tips'].values() if any(survey['blobs'][h]['collect_uses_opt_out_distinction'] for _,h in t['modules']) for i in t['pr_ids']) == [282,283,284]
    if args.self_test:
        for src,mut in [(0,lambda x:x[2]['real_exec'].pop()),(1,lambda x:x[2].update(value='29')),(2,lambda x:x[1].update(observed_rustc=x[0]['observed_rustc'])),(3,lambda x:x['objects'][0].update(bytes=42))]:
            a=deepcopy([r,s,d,f]);mut(a[src]);
            try:check(*a)
            except AssertionError:continue
            raise AssertionError('mutation accepted')
    print('Verified nine ordinary Ruff builds, 28 Cargo mode/compile controls, six real one-option compiler/linker replays, and 297 published heads.')


if __name__ == '__main__':
    main()
