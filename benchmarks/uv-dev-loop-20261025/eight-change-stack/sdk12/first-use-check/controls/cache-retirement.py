"""Retain only the private document cache before a first-use endpoint.

No target, shared compiler state or registry source is removed. Retired records
remain inside the execution manifest, and no token or counter is accessed here.
"""
from pathlib import Path
import hashlib
import json
import os
import re
import stat


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def retire(home, arm, execution, label, witness):
    home, execution = Path(home), Path(execution)
    assert arm in ('baseline', 'candidate')
    assert re.fullmatch(r'(?:native|profile|pair-[0-7]-[01]-(?:baseline|candidate))', label)
    before = witness.observe(home, arm)
    destination = execution / 'retired-registry-cache' / label
    assert not os.path.lexists(destination)
    retired = None
    if arm == 'candidate':
        original = home / witness.DIRECTORY
        original_stat = original.lstat()
        assert stat.S_ISDIR(original_stat.st_mode) and original_stat.st_uid == os.geteuid()
        destination.parent.mkdir(mode=0o700, exist_ok=True)
        assert not destination.parent.is_symlink()
        assert destination.parent.stat().st_dev == original_stat.st_dev
        original.rename(destination)
        assert destination.stat().st_ino == original_stat.st_ino
        retired = str(destination)
    after = witness.observe(home, arm, require_populated=False)
    assert after['present'] is False
    record = {'state': 'private-document-cache-retained-before-endpoint', 'arm': arm,
              'label': label, 'home': str(home), 'original_execution': str(execution),
              'before': before, 'after': after, 'retired_directory': retired,
              'target_shared_registry_sources_modified': False,
              'cache_records_deleted': False, 'during_counted_process': False}
    validate_reset(record, home, arm, execution, label, witness)
    path = execution / (label + '.cache-reset.json')
    with path.open('x') as stream:
        json.dump(record, stream, indent=2, sort_keys=True)
        stream.write('\n')
    return {'path': str(path), 'sha256': sha(path)}


def validate_reset(record, home, arm, execution, label, witness, original_execution=None):
    home, execution = Path(home), Path(execution)
    original = Path(original_execution) if original_execution is not None else execution
    assert record['state'] == 'private-document-cache-retained-before-endpoint'
    assert record['arm'] == arm and record['home'] == str(home) and record['label'] == label
    assert record['original_execution'] == str(original)
    assert record['target_shared_registry_sources_modified'] is False
    assert record['cache_records_deleted'] is record['during_counted_process'] is False
    witness.validate_snapshot(record['before'], home, arm)
    witness.validate_snapshot(record['after'], home, arm, require_populated=False)
    assert record['after']['present'] is False
    if arm == 'baseline':
        assert record['retired_directory'] is None
        assert not os.path.lexists(execution / 'retired-registry-cache' / label)
        return
    relative = Path('retired-registry-cache') / label
    assert record['retired_directory'] == str(original / relative)
    directory = execution / relative
    info = directory.lstat()
    assert stat.S_ISDIR(info.st_mode) and not directory.is_symlink()
    assert info.st_mode & 0o077 == 0
    entries = record['before']['entries']
    assert {path.name for path in directory.iterdir()} == {row['name'] for row in entries}
    for row in entries:
        path = directory / row['name']
        info = path.lstat()
        assert stat.S_ISREG(info.st_mode) and info.st_nlink == row['nlink'] == 1
        assert info.st_size == row['bytes'] and stat.S_IMODE(info.st_mode) == row['mode']
        assert sha(path) == row['sha256']


def validate_sample(sample, home, execution, witness, original_execution=None):
    execution = Path(execution)
    original = Path(original_execution) if original_execution is not None else execution
    arm, label = sample['variant'], sample['label']
    reference = sample['cold_cache_reset']
    assert reference['path'] == str(original / (label + '.cache-reset.json'))
    path = execution / (label + '.cache-reset.json')
    assert sha(path) == reference['sha256']
    validate_reset(json.loads(path.read_bytes()), home, arm, execution, label, witness, original)
    witness.validate_snapshot(sample['registry_cache_before'], home, arm, require_populated=False)
    assert sample['registry_cache_before']['present'] is False
    witness.validate_snapshot(sample['registry_cache_after'], home, arm)


def footprint(sample):
    after = sample['registry_cache_after']
    return {'label': sample['label'], 'arm': sample['variant'],
            'committed_entries': after['committed_slots'], 'committed_bytes': after['committed_bytes'],
            'minimum_additional_private_file_creations': after['committed_slots'],
            'minimum_additional_bytes_written': after['committed_bytes'],
            'logical_bytes_not_physical_io': True,
            'total_writes_or_syscalls_measured': False,
            'reason': 'Final committed records omit collision replacements and transient writes.'}
