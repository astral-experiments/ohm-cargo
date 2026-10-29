#!/usr/bin/env python3
"""Verify the portable stock Cargo manifest-observation evidence from one H3 study."""
import argparse
import base64
import copy
import gzip
import hashlib
import json
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
SHA = re.compile('[0-9a-f]{64}')
PHASES = ['initial','untouched','flag-edit','edit-repeat','empty-edited','restored','final-repeat']
MODS = ['initial','untouched','second-only','second-and-flag','repeat-failure','empty-both','restore']
TOOLS = {'cargo':'02a86ebd2d9e4f237b33f212102b81ed145eb77fae090d67e379cb6f1d70a573',
         'rustc':'c6ab483d6698f68eebb49d74b27361f3e02ede55452dc0416c3fdec9a45b7f60',
         'wild':'0d6335808b647d499f3d74993b602e64ff0625206c809bf4913c487eea380cd5'}
def digest(b): return hashlib.sha256(b).hexdigest()
def edit(b):
    assert b.count(b'\ntest = false\n') == 1
    return b.replace(b'\ntest = false\n',b'\n')
def sum_file(p): return digest(p.read_bytes())
def decode(s): return base64.b64decode(s,validate=True)
def need(condition, message):
    if not condition: raise AssertionError(message)
def check(root, ledger):
    assert ledger['schema'] == 1 and ledger['tools'] == TOOLS
    assert ledger['initial_errors'] == {}
    assert all(SHA.fullmatch(v) for v in ledger['raw_terminals'].values())
    assert 'build' in ledger['terminal_counts'] and ledger['terminal_counts'] == {'build':49,'check':28,'cargo_commands':77,'reopened_native_rlibs':49}
    rows = ledger['rows']
    keyed = {(r['group'],r['case'],r['mode'],r['phase']):r for r in rows}
    expected = set()
    for case in ['macro','include','wrapper','asm','module']:
        for mode in (['build','check'] if case in ['macro','include','wrapper'] else ['build'] if case == 'asm' else ['check']):
            for phase in (MODS if case=='module' else PHASES):
                expected.add(('default',case,mode,phase))
    for group in ['no-inc','ohm-off','ohm-off-no-inc']:
        expected.update((group,'asm','build',p) for p in PHASES)
    assert len(rows)==len(keyed)==77 and set(keyed)==expected
    for key, r in keyed.items():
        group, case, mode, p = key
        tag='/'.join(key)
        mf = (root/'fixture'/case/'consumer/Cargo.toml').read_bytes()
        edited = p in ['flag-edit','edit-repeat','empty-edited','second-and-flag','repeat-failure','empty-both']
        actual = edit(mf) if edited else mf
        need(r['manifest_sha256']==digest(actual) and r['metadata_target_test']==edited, tag+' manifest')
        need(r['test']==edited,tag+' flag')
        fail = case=='module' and p in ['second-and-flag','repeat-failure','empty-both']
        need(r['cargo_rc']==(101 if fail else 0) and ('E0761' in r['cargo_codes'])==fail,tag+' Cargo')
        fresh = p in ['untouched','edit-repeat','final-repeat','second-only']
        need(r['consumer_rustc']==int(not fresh),tag+' compiler')
        need(r['fresh']==(None if fail else fresh),tag+' freshness')
        need(all(SHA.fullmatch(v) for v in r['raw'].values()),tag+' receipts')
        need(all(n.startswith('events.') and SHA.fullmatch(v) for n,v in r['exec_trace_sha256'].items()),tag+' events')
        need(bool(r['exec_trace_sha256']),tag+' empty process evidence')
        need(len(r['consumer_argv'])==r['consumer_rustc'],tag+' physical argv')
        for a in r['consumer_argv']:
            need(a[a.index('--crate-name')+1]=='manifest_case',tag+' consumer')
            need('--test' not in a,tag+' production reached')
            need(('--cfg' in a and ('observed_test_on' if edited else 'observed_test_off') in a) if case=='wrapper' else True,tag+' wrapper direct rustc')
            if case=='macro':
                externs=[v.split('=',1)[0] for i,v in enumerate(a) if i and a[i-1]=='--extern']
                need(externs==['facade'],tag+' true reexport')
            if case=='asm':
                has_inc=any(z.startswith('incremental=') or z.startswith('-Cincremental=') for z in a)
                need(has_inc==(group in ['default','ohm-off']),tag+' actual IC')
        body=[d for d in r['dep_info'] if d['kind']=='rustc']
        if not fail:
            need(bool(body),tag+' missing depinfo')
            need((case=='include')==any('Cargo.toml' in d['body'] for d in body),tag+' input dep-info')
            need(not any('selected/mod.rs' in d['body'] for d in body),tag+' hidden second path')
        if case=='module' and fail:
            need('E0761' in r['diagnostics'],tag+' missing exact compiler diagnostic')
            continue
        if mode=='build':
            native=r['external']
            value=17 if not edited else 29
            if case=='asm' and group in ['default','ohm-off'] and p in ['flag-edit','edit-repeat']:
                value=17
            need(native['original_stdout']==native['reopened_stdout']==f'{value}\n',tag+' native output')
            need(native['compile']==native['run']==0 and SHA.fullmatch(native['executable_sha256']),tag+' caller')
            rl=[h for n,h in r['products'].items() if n.endswith('.rlib')]
            need(rl==[native['rlib_sha256']],tag+' archive')
            need(native['original_stdout_sha256']==native['reopened_stdout_sha256']==digest(f'{value}\n'.encode()),tag+' stdout bytes')
            if case=='asm':
                emb=native['embedded']
                data=decode(emb['base64'])
                need(emb['section']=='.rodata.manifest_fixture' and emb['member'].endswith('.o'),tag+' ELF')
                need(data==(mf if value==17 else edit(mf)),tag+' native object contents')
                need(digest(data)==emb['bytes_sha256'] and len(data)==emb['length'] and (data==actual)==emb['matches_current'],tag+' archive corroboration')
        elif not fail:
            reader=r['external']
            expected_error=case!='module' and edited
            need((reader['compile']==0)==(not expected_error),tag+' ordinary check reader')
            need(('E0308' in reader['stderr'])==expected_error,tag+' type mismatch')
            need(reader['original_stderr_sha256']==r['raw']['reader.stderr'],tag+' stderr')
    return len(rows)
def main():
    parser=argparse.ArgumentParser();parser.add_argument('--mutations',action='store_true');opts=parser.parse_args()
    actual={p.relative_to(HERE).as_posix():sum_file(p) for p in HERE.rglob('*') if p.is_file() and p.name!='SHA256SUMS' and '__pycache__' not in p.parts}
    maps={name:sha for sha,name in (l.split('  ',1) for l in (HERE/'SHA256SUMS').read_text().splitlines())}
    assert actual==maps
    ledger=json.loads(gzip.decompress((HERE/'evidence.json.gz').read_bytes()))
    n=check(HERE,ledger)
    if opts.mutations:
        def select(d,case,mode,phase,group='default'):
            return next(r for r in d['rows'] if (r['group'],r['case'],r['mode'],r['phase'])==(group,case,mode,phase))
        for mutate in [lambda d:select(d,'macro','build','flag-edit')['external'].update(reopened_stdout='17\n'),
                       lambda d:select(d,'module','check','second-and-flag').update(cargo_rc=0),
                       lambda d:select(d,'include','check','initial').update(dep_info=[]),
                       lambda d:select(d,'asm','build','flag-edit','no-inc')['external']['embedded'].update(base64=base64.b64encode(b'false').decode())]:
            modified=copy.deepcopy(ledger);mutate(modified)
            try: check(HERE,modified)
            except (AssertionError,ValueError): pass
            else: raise AssertionError('invalid evidence accepted')
    print(f'{n} stock Cargo commands, 49 separately copied archives compiled into executable readers, 28 external metadata/compiler cases, four assembly modes verified.')
if __name__=='__main__':main()
