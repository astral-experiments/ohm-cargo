"""Bounded, read-only witness of the candidate's actual private registry cache.

This inventories committed source-generated records. It does not claim a hit
count or independently recompute the keyed BLAKE3 codec checksum.
"""
from pathlib import Path
import hashlib
import json
import os
import re
import stat

MAGIC = b'ohm-registry-json-v1\0'
DIRECTORY = '.ohm-registry-json-v1'
MAX_ENTRY = 64 * 1024
MAX_SLOTS = 4096


def _digest(value):
    assert isinstance(value, str) and re.fullmatch(r'[0-9a-f]{64}', value)
    return value


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        assert key not in result
        result[key] = value
    return result


def _reject_number(value):
    raise AssertionError('non-TOML JSON number')


def _supported(value, depth=0):
    assert depth <= 32
    if isinstance(value, dict):
        for key, child in value.items():
            assert isinstance(key, str) and key != '$__toml_private_datetime'
            _supported(child, depth + 1)
    elif isinstance(value, list):
        for child in value:
            _supported(child, depth + 1)
    elif type(value) is int:
        assert -(2**63) <= value < 2**63
    else:
        assert type(value) in (str, bool)


def _inventory_digest(entries):
    return hashlib.sha256(json.dumps(entries, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def validate_snapshot(row, home, arm, require_populated=True):
    home = Path(home)
    assert arm in ('baseline', 'candidate')
    assert row['schema'] == 1 and row['arm'] == arm
    assert row['home'] == str(home) and row['directory'] == str(home / DIRECTORY)
    entries = row['entries']
    assert len(entries) == row['committed_slots'] <= MAX_SLOTS
    assert [entry['name'] for entry in entries] == sorted({entry['name'] for entry in entries})
    assert row['committed_bytes'] == sum(entry['bytes'] for entry in entries) <= MAX_SLOTS * MAX_ENTRY
    assert row['inventory_sha256'] == _inventory_digest(entries)
    assert row['keyed_blake3_rechecked'] is False and row['hit_count_claimed'] is False
    if arm == 'baseline':
        assert row['present'] is False and not entries
    else:
        assert row['present'] is True or (not require_populated and not entries)
        if require_populated:
            assert entries
    for entry in entries:
        assert re.fullmatch(r'[0-9a-f]{3}', entry['name'])
        assert len(MAGIC) + 64 < entry['bytes'] <= MAX_ENTRY
        assert entry['mode'] & 0o077 == 0 and entry['uid'] == row['uid'] and entry['nlink'] == 1
        assert int(entry['key'][:4], 16) >> 4 == int(entry['name'], 16)
        for field in ('sha256', 'key', 'codec_digest', 'payload_sha256'):
            _digest(entry[field])
        assert entry['json_shape_validated'] is True
    return True


def observe(home, arm, require_populated=True):
    home = Path(home)
    assert home.is_absolute() and home.resolve(strict=True) == home
    assert home.is_dir() and not home.is_symlink()
    uid = os.geteuid()
    directory = home / DIRECTORY
    present = os.path.lexists(directory)
    row = {'schema': 1, 'home': str(home), 'directory': str(directory), 'arm': arm,
           'uid': uid, 'present': present, 'entries': [], 'keyed_blake3_rechecked': False,
           'hit_count_claimed': False}
    if arm == 'baseline':
        assert not present
    elif present:
        for parent in (home, *home.parents):
            info = parent.lstat()
            assert stat.S_ISDIR(info.st_mode) and info.st_uid in (0, uid)
            assert info.st_mode & 0o022 == 0 or (info.st_uid == 0 and info.st_mode & 0o1000)
        info = directory.lstat()
        assert stat.S_ISDIR(info.st_mode) and info.st_uid == uid and info.st_mode & 0o077 == 0
        paths = sorted(directory.iterdir())
        assert len(paths) <= MAX_SLOTS
        for path in paths:
            assert re.fullmatch(r'[0-9a-f]{3}', path.name)
            fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC)
            try:
                before = os.fstat(fd)
                assert stat.S_ISREG(before.st_mode) and before.st_uid == uid
                assert before.st_nlink == 1 and before.st_mode & 0o077 == 0
                assert len(MAGIC) + 64 < before.st_size <= MAX_ENTRY
                data = bytearray()
                while len(data) <= MAX_ENTRY:
                    chunk = os.read(fd, MAX_ENTRY + 1 - len(data))
                    if not chunk:
                        break
                    data.extend(chunk)
                after = os.fstat(fd)
                fields = ('st_dev', 'st_ino', 'st_size', 'st_mtime_ns', 'st_ctime_ns', 'st_mode', 'st_uid', 'st_nlink')
                assert all(getattr(before, field) == getattr(after, field) for field in fields)
                assert len(data) == before.st_size and data.startswith(MAGIC)
            finally:
                os.close(fd)
            data = bytes(data)
            key = data[len(MAGIC):len(MAGIC) + 32]
            codec_digest = data[len(MAGIC) + 32:len(MAGIC) + 64]
            payload = data[len(MAGIC) + 64:]
            value = json.loads(payload, object_pairs_hook=_unique_object,
                               parse_float=_reject_number, parse_constant=_reject_number)
            assert isinstance(value, dict)
            _supported(value)
            row['entries'].append({'name': path.name, 'bytes': len(data),
                'mode': stat.S_IMODE(before.st_mode), 'uid': uid, 'nlink': before.st_nlink,
                'sha256': hashlib.sha256(data).hexdigest(), 'key': key.hex(),
                'codec_digest': codec_digest.hex(), 'payload_sha256': hashlib.sha256(payload).hexdigest(),
                'json_shape_validated': True})
    row['committed_slots'] = len(row['entries'])
    row['committed_bytes'] = sum(entry['bytes'] for entry in row['entries'])
    row['inventory_sha256'] = _inventory_digest(row['entries'])
    validate_snapshot(row, home, arm, require_populated)
    return row
