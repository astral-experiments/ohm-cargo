"""Offline positive and refusal checks; no Cargo, guest, counters or timers."""
from pathlib import Path
import hashlib
import importlib.util
import json
import os
import tempfile

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('write_decoder', HERE / 'decode_writes.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
os.umask(0o077)
os.sched_setaffinity(0, set(range(24, 32)))
smoke = HERE / 'capability-smoke-02'
cache = smoke / '.ohm-registry-json-v1'
source, = smoke.glob('trace.[0-9]*')
original = source.read_text()
final = {p.name: p for p in cache.iterdir()}
expected = json.loads((smoke / 'expected.json').read_bytes())
checks = []


def replay(text, extra=None, final_files=final):
    with tempfile.TemporaryDirectory(prefix='write-witness-', dir='/tmp') as temporary:
        path = Path(temporary) / 'trace.1'
        path.write_text(text)
        paths = [path]
        if extra is not None:
            other = Path(temporary) / 'trace.2'
            other.write_text(extra)
            paths.append(other)
        return module.decode(paths, cache, final_files)


def refuse(label, text, **kwargs):
    try:
        replay(text, **kwargs)
    except (AssertionError, ValueError, KeyError):
        checks.append({'case': label, 'refused': True})
    else:
        raise AssertionError(label)


actual = replay(original)
assert actual['successful_logical_write_bytes'] == expected['successful_logical_write_bytes'] == 330
assert actual['successful_commits'] == expected['commits'] == 3
assert actual['final_slots'] == expected['final']
assert actual['final_logical_bytes'] == 211
assert len(actual['short_writes']) == len(actual['failed_writes']) == 1
assert actual['short_writes'][0]['requested'] == 32 and actual['short_writes'][0]['returned'] == 16
assert actual['failed_writes'][0]['error'] == 'EFBIG'
checks.append({'case': 'actual-binary-write-writev-pwrite-replacement-short-failed-and-final-payloads', 'passed': True})
assert module.cbytes('"\\0\\377\\x80é"') == b'\0\xff\x80\xc3\xa9'
checks.append({'case': 'binary-NUL-octal-hex-UTF8-strings', 'passed': True})
first = actual['writes'][0]['raw']
prefix, suffix = first.split(', ', 1)
joined = prefix + ', <unfinished ...>\n<... write resumed>' + suffix
assert replay(original.replace(first, joined, 1))['successful_logical_write_bytes'] == 330
checks.append({'case': 'named-per-PID-unfinished-resumed-preserves-local-order', 'passed': True})
refuse('unidentified-event', original + '???( <unfinished ...>\n')
refuse('unfinished-without-resume', original.replace(first, prefix + ', <unfinished ...>', 1))
refuse('wrong-named-resume', original.replace(first, joined.replace('<... write resumed>', '<... read resumed>'), 1))
refuse('unpaired-resume', original + '<... write resumed>) = 1\n')
refuse('missing-write-fd-path', original.replace(first, first.replace(first.split('(', 1)[1].split(', ', 1)[0], '3', 1), 1))
refuse('truncated-write-string', original.replace(first, first.replace(', 21)', '..., 21)', 1), 1))
refuse('return-exceeds-request', original.replace(first, first.rsplit('= ', 1)[0] + '= 22', 1))
refuse('unexpected-writer-fd', original.replace(first, first.replace('write(3<', 'write(999<', 1), 1))
commit = [line for line in original.splitlines() if line.startswith('rename(') and str(cache / '001') in line][-1]
refuse('missing-final-commit', original.replace(commit + '\n', '', 1))
refuse('two-cache-mutating-PIDs', original, extra=original)
refuse('wrong-final-slot-inventory', original, final_files={'001': final['001']})
refuse('successful-direct-committed-slot-write', original + f'write(3<{cache}/001>, "x", 1) = 1\n')
refuse('successful-cache-truncate', original + f'truncate("{cache}/001", 0) = 0\n')
refuse('successful-unobserved-source-commit', original + f'rename("{cache}/.tmp-unknown", "{cache}/003") = 0\n')
assert replay(original + f'write(1</dev/null<char 1:3>>, "{cache}", {len(str(cache))}) = {len(str(cache))}\n')['successful_logical_write_bytes'] == 330
checks.append({'case': 'cache-path-in-unrelated-output-is-not-a-cache-write', 'passed': True})
report = {'state': 'bounded-write-decoder-synthetic-checks-passed', 'checks': checks,
          'source_sha256': hashlib.sha256((HERE / 'decode_writes.py').read_bytes()).hexdigest(),
          'actual_trace_sha256': hashlib.sha256(source.read_bytes()).hexdigest(),
          'guest_calls': 0, 'Cargo_calls': 0, 'profile_metrics_opened': False,
          'limitations': ['A single cache-mutating PID is required; no global order inferred.',
                          'Unsupported cache mutations or unresolved events refuse exact accounting.',
                          'Only logical syscall bytes are counted; physical I/O is not inferred.']}
print(json.dumps(report, indent=2, sort_keys=True))
