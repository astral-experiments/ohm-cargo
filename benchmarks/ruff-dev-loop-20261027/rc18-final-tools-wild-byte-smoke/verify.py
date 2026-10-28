import hashlib
import json
from pathlib import Path
import re
import subprocess
import tarfile
import tempfile

root=Path(__file__).resolve().parent
sha=lambda data:hashlib.sha256(data).hexdigest()
with tarfile.open(root/'native.tar.gz') as archive:
    data={m.name:archive.extractfile(m).read() for m in archive if m.isfile()}
read=lambda s:json.loads(data[s]);result=read('complete.json')
assert data['package-smoke-v1.exit'].strip()==b'0' and not data['package-smoke-v1.stderr']
assert json.loads(data['package-smoke-v1.stdout'])==result
assert result['cargo']=='cfc66a7ceee5cad8f8939245d359e4db0d2b6f2abb5760c7cbefa6c9a1d454f8'
assert result['rust_driver']=='22abce6921b46f93f387c7d3d99cefa4df9c0a866619447077699ef81a73827f'
assert result['wild']=='9de3bdd6675f02e08d687045383c097ab0ef6027c779f153a7823153ecf8445e'
assert result['compiler_flags']==[] and result['gcc']=='1b99826121ae6682a634e5efe09bd3e3df58ce58e0b28f849114ab5b89139c26'
assert sha(data['smoke-test-release.sh'])==result['source_script_sha256']=='8e112d810a1f3f4f6fd5c73233aa84f7a911eb8eeeaafbd27d466441ee53a888'
assert sha(data['original-fixture.sh'])==result['exact_fixture_sha256'] and data['original-fixture.sh'] in data['smoke-test-release.sh']
assert sha(data['original-stanza.sh'])==result['exact_stanza_sha256'] and data['original-stanza.sh'] in data['smoke-test-release.sh']
assert data['run-package-stanza.sh']==b'set -euo pipefail\n'+data['original-fixture.sh']+data['original-stanza.sh']
assert bytes.fromhex(result['tmpdir_bytes']).endswith(b'/tmp-\xff')
assert bytes.fromhex(result['cases']['library-raw']['library_path_bytes']).endswith(b'/lib-\xff')
assert bytes.fromhex(result['cases']['library-unicode-decoy']['library_path_bytes']).endswith(b'/lib-\xef\xbf\xbd')
assert data['native-fixture/raw.a']!=data['native-fixture/unicode-decoy.a']
for case,count,want in [('package-raw-tmpdir',2,b''),('library-raw',1,b'41\n'),('library-unicode-decoy',1,b'99\n')]:
    r=result['cases'][case]; key=case+'/'
    assert r['exit']==0 and data[key+'exit'].strip()==b'0' and data[key+'stdout']==want==bytes.fromhex(r['stdout_hex'])
    assert sha(data[key+'exec.trace'])==r['trace'] and sha(data[key+'elf-comment'])==r['comment']
    assert sha(data[key+'native.elf'])==r['elf'] and data[key+'native.elf'].startswith(b'\x7fELF')
    successful=[l for l in data[key+'exec.trace'].splitlines() if re.search(rb'execve\("[^"\n]*/wild-ld/ld\.bfd",',l) and l.rstrip().endswith(b'= 0')]
    assert len(successful)==r['wild_executions']==count and data[key+'wild-execs']==b'\n'.join(successful)+b'\n'
    with tempfile.NamedTemporaryFile() as f:
        f.write(data[key+'native.elf']);f.flush()
        assert subprocess.check_output(['readelf','--string-dump=.comment',f.name])==data[key+'elf-comment']
    assert b'Wild' in data[key+'elf-comment']
print('Verified exact package smoke, three native ELF files, 4 physical Wild jobs, raw=41 and Unicode=99.')
