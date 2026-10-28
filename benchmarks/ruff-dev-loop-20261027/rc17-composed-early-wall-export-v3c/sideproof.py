"""Cross-check independent native and H2 terminal evidence without opening their wall samples."""
import hashlib
import re

H2_PLAN='44c3e6db80242b5461bbb3f86f2fae5a0f166a45'
H2_RESULT='rc17-text-size-first-selection-wall-results'
NATIVE_READER='ec0d86f448c442168b7407fff3814a9b1cdfe05d26b77795f7c80467f191b758'
ORIGINAL_VERIFIER='ef9d5f2ae76597aea7070ca978909d7fa38ec69a369b4ad2ca058642ed8aca35'
def check_native(w,view,hashes):
    assert w['read_only'] is True and w['counted_clocks']==0 and w['original_verifier_sha256']==ORIGINAL_VERIFIER
    assert (w['reopened_unique_stock_processes'],w['explicit_processes'],w['ordinary_controls'])==(9867,9568,299)
    output={r['evidence']['file']:r['evidence']['sha256'] for r in view['targets'].values()}
    assert len(output)==50 and all(re.fullmatch(r'targets/[^/]+/all-widths\.json',f) for f in output)
    output.update({'terminal.json':hashes['terminal_sha256'],'wall-view.json':hashes['view_sha256'],'independent.json':hashes['verifier_receipt_sha256']})
    assert w['byte_recomputed_outputs']==output
    assert w['previous_v2_startup_failure_sha256']=='89caf4045b6b3a8a76c48cf959f9603a9814cc4d2931504e134afaa62ef5f127'
    assert w['full_predecessor_commitment']=='4b91f1b8d572612351ea5261e0bd3fdc0444ebc62d18ec64e51a3a4cf0cd0237'
def check_h2(host,name,terminal_sha):
    assert host['kind']=='result' and host['registration']['wall_ref']==H2_PLAN
    assert (host['terminal_file'],host['terminal_sha256'])==(name,terminal_sha)
    expected=host['role_exits'];logs=host['role_logs']
    assert set(logs)==set(expected)=={'admit','score','verify'} and expected['admit']==expected['verify']==0 and type(expected['score']) is int
    assert all(set(r)=={'out','err','exit'} and all(re.fullmatch('[0-9a-f]{64}',h) for h in r.values()) for r in logs.values())
    assert all(hashlib.sha256(str(code).encode()).hexdigest()==logs[role]['exit'] for role,code in expected.items())
    assert (name=='terminal.json' and expected['score']==0) or (name=='failure.txt' and expected['score']!=0)
    assert 0<host['ended_unix_ns']<=host['verified_unix_ns']
    return (expected['score'],host['ended_unix_ns'],host['verified_unix_ns'])
