"""Read the seven retained outputs of replay_one.py in controls mode, ignoring timing fields."""
from pathlib import Path
import argparse
import hashlib
import json
import re

A = 'b5dba861cc38e3f7fb4524c9ceba3e01a474ea13'
B = '7b13f01ba1569887a25670820764b24c206da8e5'
STATES = [('empty-B', B), ('first-A', A), ('return-B', B), ('return-A', A), ('invalid-A', A), ('recovered-A', A), ('unchanged-A', A)]
TESTS = ('tests::basic', 'tests::string_processing', 'comments::tests::parenthesized_expression')
COMMAND = ['cargo', '+ohm', 'test', '-p', 'ruff_python_formatter', '--lib', '--no-run', '--locked', '--offline', '-j4', '--message-format=json']
def sha(path):
    with path.open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()
def read(path):
    return json.loads(path.read_bytes())
def lines(path):
    return [json.loads(line) for line in path.read_bytes().splitlines()]
def scope(path):
    result=read(path)
    return {name:result[name] for name in ('cargo','rustc','driver','stock_wild','source','cpus')}
def error_code(record):
    code=record.get('code')
    return code['code'] if code else None
def check(root):
    results=read(root/'results.json')
    assert set(results)=={k for k,_ in STATES}
    data={'revisions':{'A':A,'B':B},'identity':scope(root/'identity.json'),'history_sha256':sha(root/'results.json'),'commands':[],'executables':{}}
    for key,rev in [('A',A),('B',B)]:
        p=root/(rev+'.elf')
        with p.open('rb') as f:assert f.read(4)==b'\x7fELF'
        data['executables'][key]={'sha256':sha(p),'bytes':p.stat().st_size}
    for name,rev in STATES:
        d=root/name
        rc=101 if name=='invalid-A' else 0
        call=read(d/'cargo.json');assert call['argv']==COMMAND and call['exit']==rc==results[name]['exit']
        stream=lines(d/'cargo.stdout');assert stream[-1]=={'reason':'build-finished','success':not rc}
        messages=[m['message'] for m in stream if m['reason']=='compiler-message']
        errors=[m for m in messages if m['level']=='error']
        artifacts=[m for m in stream if m['reason']=='compiler-artifact']
        selected=sorted(m['target']['name'] for m in artifacts if not m['fresh']);assert all(re.fullmatch(r'[A-Za-z0-9_-]+',n) for n in selected)
        raw={p.name:sha(p) for p in sorted(d.iterdir()) if p.is_file()};assert all(re.fullmatch(r'[A-Za-z0-9_.-]+',n) for n in raw)
        row={'case':name,'source':rev,'exit':rc,'artifacts':len(artifacts),'dirty':selected,'raw_sha256':raw};data['commands'].append(row)
        if rc:
            assert len(errors)==1 and error_code(errors[0])=='E0308'
            span,=[s for s in errors[0]['spans'] if s['is_primary']];assert span['file_name']=='crates/ruff_python_formatter/src/lib.rs' and any('OHM_FORMATTER_BRANCH_TYPE_GUARD' in t['text'] for t in span['text'])
            row['native_error']={'code':'E0308','file':span['file_name'],'line':span['line_start'],'column':span['column_start']}
            continue
        assert not errors and len(artifacts)==216 and selected==results[name]['dirty']
        own,=[m for m in artifacts if m['target']['name']=='ruff_python_formatter' and m['profile']['test'] and m.get('executable')];assert own
        key='A' if rev==A else 'B';row['ELF']=results[name]['ELF'];assert row['ELF']==data['executables'][key]['sha256']
        inventory=sorted(l.removesuffix(': test') for l in (d/'list.stdout').read_text().splitlines() if l.endswith(': test'));assert len(inventory)==len(set(inventory))==53 and set(TESTS)<=set(inventory)
        row['inventory']=sha(d/'list.stdout');assert row['inventory']==results[name]['inventory'];row['test_names']=inventory
        row['exact_tests']=[]
        for i,test in enumerate(TESTS):
            label=f'test-{i}'; cmd=read(d/(label+'.json'));assert cmd['exit']==0 and cmd['argv'][1:]==['--exact',test,'--test-threads=1']
            printed=(d/(label+'.stdout')).read_text();assert re.search(r'^test '+re.escape(test)+r' \.\.\. ok$',printed,re.M) and '1 passed; 0 failed;' in printed
            row['exact_tests'].append(test)
        row['abi']={}
        for n in (64,56):
            label=f'size-{n}';cmd=read(d/(label+'.json')); assert cmd['argv'][:2]==['rustc','+ohm'] and '--extern' in cmd['argv']
            good=n==(64 if key=='A' else 56);assert cmd['exit']==(0 if good else 1)
            diag=[error_code(x) for x in lines(d/(label+'.stderr')) if x.get('level')=='error' and error_code(x)]
            assert diag==([] if good else ['E0308']);row['abi'][str(n)]={'exit':cmd['exit'],'diagnostics':diag}
        if name=='empty-B':
            p=d/'all-tests.stdout';lines0=p.read_text().splitlines();assert read(d/'all-tests.json')['exit']==0 and any('51 passed; 0 failed; 2 ignored;' in line for line in lines0)
            row['suite']={'passed':51,'failed':0,'ignored':2,'stdout':sha(p)}
    return data
if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('results',type=Path);args=ap.parse_args();print(json.dumps(check(args.results),sort_keys=True,separators=(',',':')))
