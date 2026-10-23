"""Exact preflight output pins and the one reviewed archive-name transformation."""
from pathlib import Path
import hashlib
import re
import stat

def digest(data):
    return hashlib.sha256(data).hexdigest()

# Exact existing read-only archive decoder; source reuse is recorded in the freeze.
def archive_members(raw):
 assert raw.startswith(b'!<arch>\n'),'unsupported archive container'
 position=8;names=b'';members=[]
 while position<len(raw):
  header=raw[position:position+60];assert len(header)==60 and header[58:60]==b'`\n'
  size=int(header[48:58].strip());name=header[:16].rstrip().decode('ascii');start=position+60
  data=raw[start:start+size];assert len(data)==size
  position=start+size+(size%2)
  if name=='//':names=data;kind='archive-name-table'
  elif name in ('/','/SYM64/'):kind='archive-symbol-index'
  else:
   if name.startswith('#1/'):
    length=int(name[3:]);name=data[:length].rstrip(b'\0').decode();data=data[length:]
   elif name.startswith('/') and name[1:].isdigit():
    offset=int(name[1:]);assert offset<len(names)
    end=names.find(b'/\n',offset);assert end>=offset;name=names[offset:end].decode()
   else:name=name.removesuffix('/')
   if name.endswith('.rmeta') or name=='lib.rmeta':kind='rust-metadata'
   elif data.startswith(b'\x7fELF'):kind='native-elf'
   elif data.startswith(b'BC\xc0\xde') or data.startswith(b'\xde\xc0\x17\x0b'):kind='native-bitcode'
   elif name.startswith('__.SYMDEF'):kind='archive-symbol-index'
   else:kind='other-member'
  members.append({'ordinal':len(members),'name':name,'kind':kind,'bytes':len(data),'sha256':digest(data)})
 assert position==len(raw),'archive trailing bytes differ'
 return members


def inspect_output(spec):
    path = Path(spec['path'])
    metadata = path.lstat()
    assert stat.S_ISREG(metadata.st_mode)
    raw = path.read_bytes()
    identity = {'path': str(path), 'bytes': len(raw), 'mode': stat.S_IMODE(metadata.st_mode),
                'sha256': digest(raw)}
    assert all(identity[key] == spec[key] for key in ('path', 'bytes', 'mode'))
    record = {'identity': identity, 'kind': spec['kind']}
    if spec['kind'] == 'exact':
        assert identity['sha256'] in spec['sha256']
        return record
    assert spec['kind'] == 'uv-rlib'
    reference = Path(spec['reference']['path']).read_bytes()
    assert digest(reference) == spec['reference']['sha256']
    actual_members, reference_members = archive_members(raw), archive_members(reference)
    assert len(actual_members) == len(reference_members) == 206
    assert [x['name'] for x in actual_members[:4]] == ['/', '//', 'lib.rmeta', 'lib.rmeta-link']
    assert [x['name'] for x in reference_members[:4]] == ['/', '//', 'lib.rmeta', 'lib.rmeta-link']
    names = []
    suffixes = [set(), set()]
    for actual, expected in zip(actual_members[4:], reference_members[4:]):
        assert actual['kind'] == expected['kind'] == 'native-elf'
        assert actual['bytes'] == expected['bytes'] and actual['sha256'] == expected['sha256']
        matches = [re.fullmatch(r'(uv-1423aea77971a7c7\.[a-z0-9]+\.)([a-z0-9]{7})(\.rcgu\.o)', x['name'])
                   for x in (actual, expected)]
        assert all(matches) and matches[0][1] == matches[1][1]
        for index, match in enumerate(matches):
            suffixes[index].add(match[2])
        names.append((actual['name'].encode(), expected['name'].encode()))
    assert len(names) == 202 and all(len(values) == 1 for values in suffixes)
    # Every byte must equal the authenticated per-arm archive, except those exact
    # member names in its long-name table and excluded relink-metadata wrapper.
    position = 8
    canonical = bytearray(raw[:8])
    for index in range(206):
        header = raw[position:position + 60]
        assert header == reference[position:position + 60]
        size = int(header[48:58].strip())
        start = position + 60
        payload = raw[start:start + size]
        if index in (1, 3):
            for actual, expected in names:
                assert payload.count(actual) == 1
                payload = payload.replace(actual, expected)
        assert payload == reference[start:start + size]
        end = start + size + size % 2
        padding = raw[start + size:end]
        assert padding == reference[start + size:end]
        canonical.extend(header + payload + padding)
        position = end
    assert position == len(raw) == len(reference) and bytes(canonical) == reference
    record.update(canonical_sha256=digest(canonical), ordered_native_objects=202,
                  reference_sha256=spec['reference']['sha256'])
    return record


def validate_records(records, specs):
    assert len(records) == len(specs)
    for row, spec in zip(records, specs):
        identity = row['identity']
        assert all(identity[key] == spec[key] for key in ('path', 'bytes', 'mode'))
        assert row['kind'] == spec['kind']
        assert re.fullmatch('[0-9a-f]{64}', identity['sha256'])
        if spec['kind'] == 'exact':
            assert identity['sha256'] in spec['sha256']
        else:
            assert spec['kind'] == 'uv-rlib' and row['ordered_native_objects'] == 202
            assert row['canonical_sha256'] == row['reference_sha256'] == spec['reference']['sha256']

