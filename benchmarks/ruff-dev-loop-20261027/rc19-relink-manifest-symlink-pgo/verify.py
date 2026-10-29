import json
from pathlib import Path
r=Path(__file__).resolve().parent
builds=json.loads((r/'builds.json').read_bytes())
assert builds['fixed']['commit']=='5394ce8817e224971230b80a9066cc28d504ff94'
assert builds['parent']['commit']=='a8f0c9aa0412aa259c686416a48aa8d2cf92da72'
assert builds['fixed']['compilers']==builds['parent']['compilers']
for name, b in builds.items():
    assert (b['ordered_externs'],b['linker_inputs'],b['rlibs'])==(239,335,326)
    for compiler in b['compilers']:
        rows=json.loads((r/f'{name}-{compiler}.json').read_bytes())
        assert [row['program'] for row in rows]==[17,29,31]
        assert [row['phase'] for row in rows]==['cold','during','before']
        for row in rows:
            follows=name=='parent' and row['phase']=='during'
            assert row['sentinel_replaced']==row['manifest_is_symlink']==follows
            assert (row['sentinel_sha256_before']!=row['sentinel_sha256_after'])==follows
            assert all(len(row[k])==64 for k in ['cargo_stdout_sha256','cargo_stderr_sha256'])
print('12 builds across both compilers verified, including both red and both protected interleaves')
