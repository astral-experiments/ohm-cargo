"""Verify the frozen process corpus and the actual Rust diagnostic with its three metadata inputs."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile

root = Path(__file__).resolve().parent
digests = {
    'first-occurrence-native-results-v1': '9197d1319db8a6a243eaa9a0de00ef9c26f37f4afe6310a220f5c7bff0df3251',
    'first-occurrence-lexer-definition-evidence-v1': 'fec0f6ccce49224bfa6790ff26093f41029d6cb926080e2b2ef9ca289e03cf08',
}

def sha(p):
    with p.open('rb') as f:
        return hashlib.file_digest(f,'sha256').hexdigest()

def get(p):
    return json.loads(p.read_bytes())

with tempfile.TemporaryDirectory() as tmp:
    temp = Path(tmp)
    for name, expected in digests.items():
        archive = root / (name + '.tar.gz')
        assert sha(archive) == expected
        with tarfile.open(archive) as t:
            members = t.getmembers()
            assert len({m.name for m in members}) == len(members) and sum(m.size for m in members) < 96 << 20
            for m in members:
                p = Path(m.name)
                assert (m.isfile() or m.isdir()) and not p.is_absolute() and '..' not in p.parts and p.parts[0] == name
            t.extractall(temp, members=members, filter='data')
        p = temp/name
        subprocess.run(['sha256sum','--quiet','--check','SHA256SUMS'],cwd=p,check=True)
    commands, diagnostic = [temp/name for name in digests]
    subprocess.run([sys.executable,'-B',str(commands/'verify.py')],cwd=commands,check=True)
    plan = get(commands/'preregistered-plan.json')
    for mode, (high, low, links, native) in {'build':(35,3,6,8),'test':(93,6,62,67)}.items():
        e = get(commands/(mode+'-observations.json'))
        for label in plan['schedule']:
            for action in ('edit','restore'):
                rn = label+'-'+action
                for arm in 'BC':
                    r = e['first_occurrences'][rn][arm]
                    actual = r['process_totals']
                    cutoff = label!='lexer-pending-indentation'
                    expected = {'full':high} if not cutoff else {'full':low,'link-only':links}
                    if cutoff and arm=='C':
                        expected.update({'checked-native':2,'full':low-2})
                    assert actual==expected and r['native_totals']['wild']==native
                o=e['cross_arm'][rn]
                assert all(o[k] for k in ('same_unit_paths','same_compiler_messages','same_old_cli','same_novel_cli'))
                assert all(r['matches_after_gnu_id_and_rodata_entsize_mask'] for r in o['raw_elf_differences'].values())
    for tag, line in [('initial',1623),('edited',1620),('restored',1623)]:
        p=diagnostic/tag
        inputs, snapshot, observation=map(get,[p/'input.json',p/'snapshot.json',p/'observation.json'])
        rmeta,=p.glob('*.rmeta')
        assert sha(rmeta)==inputs['active_root_rmeta_sha256']==snapshot['rmeta_sha256']
        assert sha(p/'lexer.rs')==inputs['active_source_sha256']==snapshot['lexer_rs_sha256']
        assert sha(diagnostic/'caller.rs')==inputs['caller_source_sha256'] and inputs['returncode']==1
        assert not inputs['hash_opt_in'] and not inputs['incremental_opt_in']
        assert sha(p/'stderr.jsonl')==observation['raw_stderr_sha256']
        diagnostics=[json.loads(x) for x in (p/'stderr.jsonl').read_bytes().splitlines()]
        err,=[r for r in diagnostics if (r.get('code') or {}).get('code')=='E0061']
        primary,=[s for s in err['spans'] if s['is_primary']]
        note,=[child for child in err['children'] if child['message']=='function defined here']
        secondary,=[s for s in note['spans'] if s['file_name'].endswith('crates/ruff_python_parser/src/lexer.rs')]
        assert primary==observation['primary'] and (primary['line_start'],primary['column_start'],primary['column_end'])==(2,13,43)
        assert secondary==observation['secondary'] and (secondary['line_start'],secondary['column_start'],secondary['column_end'])==(line,8,11)
        assert (p/'lexer.rs').read_text().splitlines()[line-1].startswith('pub fn lex(')
    print('Verified 24 edit and restoration job counts, and the actual E0061 definition note at lines 1623, 1620 and 1623.')
