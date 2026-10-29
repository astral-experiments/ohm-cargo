"""Reconstruct real rustc input member files. Keep the complete expected archives out of the writer."""
from pathlib import Path
import hashlib
import json
import mmap
import re
import sys

CASES = {
    'parser': (6010742, 'd18e37b28e1cfa36623d0a26f4ecc85204fc637df8b19b1c71bd56bc30414aab', '41e385a13f3dcbcba382b6bd695d91452baf9a6968d77634f8861f31279b1d0b', 1541870),
    'formatter': (15188914, '073a455846fdf25e2c0c90bf8ad421ab10c67120ff8fee66e003539d121487ee', '0c420e7086b16d2da1df246c0bee97d5ababc01d38471406e5c4cb2c41665435', 4006018),
    'linter': (103905374, '0722ba6066473ee7b3ded0a74dda67c392f23eebbbb661eb7367d1b1f0ddb93c', 'b4b7e891212eb5251959323f3ce3dac484fc59e743ca2628b39fba2cad5d9b0e', 24771278),
}


def roster(archive):
    assert archive[:8] == b'!<arch>\n'
    pos, table, entries = 8, None, []
    while pos < len(archive):
        h = archive[pos:pos+60]
        assert len(h) == 60 and h[58:] == b'`\n'
        n = h[:16].rstrip(b' ')
        size = int(h[48:58])
        start = pos+60
        assert start+size <= len(archive)
        if n == b'//':
            table = archive[start:start+size]
        elif n not in (b'/', b'/SYM64/'):
            if n.startswith(b'/'):
                off = int(n[1:])
                n = table[off:table.index(b'/\n',off)]
            else:
                n = n.removesuffix(b'/')
            name = n.decode('ascii')
            assert re.fullmatch(r'[a-zA-Z_0-9.\-]+', name) and name not in ('.','..')
            assert archive[start:start+4] == b'\x7fELF'
            assert int(h[16:28]) == int(h[28:34]) == int(h[34:40]) == 0 and int(h[40:48],8) == 0o644
            entries.append((name, pos, start, size))
        pos = start + size + size%2
    assert pos == len(archive) and [m[0] for m in entries[:2]] == ['lib.rmeta','lib.rmeta-link']
    assert len({m[0] for m in entries}) == len(entries)
    return entries


def make(source,dest):
    result = {}
    for label,(size,before,after,suffix) in CASES.items():
        d = dest/label
        d.mkdir()
        with (source/before).open('rb') as bf, (source/after).open('rb') as af, mmap.mmap(bf.fileno(),0,access=mmap.ACCESS_READ) as b, mmap.mmap(af.fileno(),0,access=mmap.ACCESS_READ) as a:
            assert len(a) == len(b) == size and hashlib.sha256(a).hexdigest() == after and hashlib.sha256(b).hexdigest() == before
            old, new = roster(b), roster(a)
            assert len(old) == len(new) and old[2][1] == new[2][1] == suffix
            assert a[suffix:] == b[suffix:]
            rows = []
            for idx, ((pn,_,po,ps),(n,_,o,s)) in enumerate(zip(old,new,strict=True)):
                if idx < 2:
                    data = a[o:o+s]
                    assert hashlib.sha256(data).digest() != hashlib.sha256(b[po:po+ps]).digest()
                else:
                    data = b[po:po+ps]
                    assert o == po and s == ps and n != pn and data == a[o:o+s]
                with (d/n).open('xb') as f:
                    f.write(data)
                rows.append([n, hashlib.sha256(data).hexdigest(),len(data)])
            (d/'members').write_text(''.join(r[0]+'\n' for r in rows))
            result[label] = dict(size=size,before=before,after=after,suffix=suffix,objects=len(rows)-2,members=rows)
    return result


if __name__ == '__main__':
    a,b = map(Path,sys.argv[1:])
    b.mkdir()
    with (b/'provenance.json').open('x') as report:
        json.dump(make(a,b),report,sort_keys=True)

