"""Predicting all current bytes from an independent stock archive and real pre-publication names."""
import argparse
import hashlib
import json
from pathlib import Path
import re

name_pattern = re.compile(rb"(ruff_linter-[a-z0-9]+\.[a-z0-9]+)\.([a-z0-9]{7})\.rcgu\.o")
chunk = 1024 * 1024


def digest(path):
    with path.open("rb") as src:
        return hashlib.file_digest(src, "sha256").hexdigest()


def by_stem(names):
    result = {}
    for name in names:
        m = name_pattern.fullmatch(name.encode())
        if m is None or m[1] in result:
            raise ValueError("unknown or duplicated current object stem")
        result[m[1]] = m[2]
    if len(result) != 256 or len(set(result.values())) != 1:
        raise ValueError("expected 256 distinct members using one genuine compiler suffix")
    return result


def recipe(gold, witness, watch):
    assert witness["arm"] == "A" and witness["whole_file_equal"]
    assert digest(gold) == witness["oracle_sha256"] == witness["product_sha256"]
    old_names = [m["name"] for m in witness["member_inputs"][2:]]
    previous = by_stem(old_names)
    assert watch["returncode"] == 0 and [e["role"] for e in watch["events"]] == ["create", "publish", "remove"]
    assert all(e["mask"] in (0x100, 0x80) for e in watch["objects"])
    current = by_stem([e["name"] for e in watch["objects"]])
    if current.keys() != previous.keys():
        raise ValueError("current inotify stems do not match the independently generated reference")
    fields = []
    members = witness["archive_members"]
    assert [m["name"] for m in members] == ["/", "//", "lib.rmeta", "lib.rmeta-link", *old_names]
    with gold.open("rb") as g:
        for m in (members[1],members[3]):
            g.seek(m["offset"])
            data = g.read(m["size"])
            assert len(data) == m["size"] and hashlib.sha256(data).hexdigest() == m["sha256"]
            found = list(name_pattern.finditer(data))
            assert [o[0].decode() for o in found] == old_names
            for o in found:
                stem, old = o[1], o[2]
                assert old == previous[stem]
                fields.append((m["offset"] + o.start(2), old, current[stem]))
    assert len(fields) == 512 and fields == sorted(fields)
    return fields, current


def expected(gold, fields):
    with gold.open("rb") as g:
        for pos, old, new in fields:
            remaining = pos - g.tell()
            assert remaining >= 0
            while remaining:
                part = g.read(min(chunk, remaining))
                assert part
                yield part
                remaining -= len(part)
            assert g.read(len(old)) == old
            yield new
        while part := g.read(chunk):
            yield part


def verify(gold, witness, watch, actual):
    fields, current = recipe(gold, witness, watch)
    h = hashlib.sha256()
    for data in expected(gold, fields):
        h.update(data)
    # Finish computing the expected whole-file digest before the first access to the product.
    predicted = h.hexdigest()
    actual_sha = hashlib.sha256()
    size = 0
    with actual.open("rb") as product:
        for data in expected(gold, fields):
            observed = product.read(len(data))
            if observed != data:
                diff = next((i for i, (x,y) in enumerate(zip(data,observed)) if x != y), len(observed))
                raise ValueError(f"current archive differs from sealed reference at byte {size + diff}; expected SHA-256 {predicted}")
            actual_sha.update(observed)
            size += len(observed)
        if product.read(1):
            raise ValueError("current archive had bytes after the complete expected stream")
    assert size == witness["bytes"] and predicted == actual_sha.hexdigest()
    return {"literal_equal":True,"bytes":size,"expected_sha256":predicted,"actual_sha256":actual_sha.hexdigest(),
            "reference_sha256":witness["oracle_sha256"],"fields":len(fields),"objects":len(current),
            "current_nonce":next(iter(current.values())).decode(),
            "names_sha256":hashlib.sha256(b"\0".join(sorted(v["name"].encode() for v in watch["objects"]))).hexdigest()}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("gold",type=Path)
    parser.add_argument("witness",type=Path)
    parser.add_argument("watch",type=Path)
    parser.add_argument("actual",type=Path)
    a=parser.parse_args()
    print(json.dumps(verify(a.gold,json.loads(a.witness.read_bytes()),json.loads(a.watch.read_bytes()),a.actual),sort_keys=True))
