"""Pure ordered-rustc-argv checks; no file, process, host, or metric access."""
from collections import Counter
import hashlib
from itertools import product
import json
from pathlib import PurePosixPath
import re
import shlex

STAGES = {'check': {'source': 1}, 'test': {'source': 2, 'rlink': 4}}
AXES = ('workload', 'assignment', 'metric', 'variant')
CELLS = set(product(('test', 'check'), ('forward', 'reverse'),
                    ('native', 'ir'), ('baseline', 'candidate')))
BASE_BINDING = {'workload', 'compiler_path', 'compiler_sha256', 'configured_cwd',
                'configured_common_environment_sha256', 'target_dir', 'build_dir'}
PROTOCOL_SHA256 = '7f3ed92b608867703a223c7a78c5af3198fd885ee8cef8c6a89967b5ae8d1bbc'


def need(condition, message):
    if not condition:
        raise ValueError(message)


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True)


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def absolute(value):
    need(isinstance(value, str) and value.startswith('/') and value != '/'
         and str(PurePosixPath(value)) == value
         and not any(part in ('.', '..', '') for part in value.split('/')[1:])
         and '\x00' not in value, 'noncanonical absolute path')
    return value


def binding_check(binding, namespace=True):
    keys = BASE_BINDING | ({'workspace_namespace'} if namespace else set())
    need(type(binding) is dict and set(binding) == keys, 'binding fields differ')
    need(binding['workload'] in STAGES, 'unknown workload')
    for key in ('compiler_path', 'configured_cwd', 'target_dir', 'build_dir'):
        absolute(binding[key])
    for key in ('compiler_sha256', 'configured_common_environment_sha256'):
        need(isinstance(binding[key], str) and re.fullmatch('[0-9a-f]{64}', binding[key]), 'invalid context digest')
    left, right = binding['target_dir'], binding['build_dir']
    need(left != right and not left.startswith(right + '/') and not right.startswith(left + '/'),
         'overlapping target/build prefixes')
    if namespace:
        need(isinstance(binding['workspace_namespace'], str)
             and re.fullmatch('[0-9a-f]{16}', binding['workspace_namespace']), 'invalid exact workspace namespace')


def normalize_path(value, binding):
    for key, label in (('target_dir', '@target'), ('build_dir', '@build')):
        root = binding[key]
        if value == root or value.startswith(root + '/'):
            absolute(value)
            suffix = value[len(root):]
            workspace = '/debug/build/workspaces/'
            if key == 'target_dir' and suffix.startswith(workspace):
                parts = suffix[len(workspace):].split('/')
                need(parts[0] == binding['workspace_namespace'], 'unexpected workspace namespace')
                parts[0] = '@workspace'
                suffix = workspace + '/'.join(parts)
            return label + suffix
    return value


def normalize_operand(option, value, binding):
    path = lambda text: normalize_path(text, binding)
    if option in ('--out-dir', '--sysroot', '-o'):
        return path(value)
    if option == '-L':
        if value.startswith('/'):
            return path(value)
        kind, equal, rest = value.partition('=')
        return kind + equal + path(rest) if equal and kind in ('all', 'dependency', 'crate', 'native', 'framework') else value
    if option == '--extern':
        name, equal, rest = value.partition('=')
        return name + equal + path(rest) if equal else value
    if option == '--emit':
        return ','.join(name + equal + path(rest) if equal else name
                        for name, equal, rest in (part.partition('=') for part in value.split(',')))
    if option == '--remap-path-prefix':
        left, equal, right = value.partition('=')
        need(equal, 'incomplete remap-path-prefix')
        return path(left) + equal + path(right)
    if option == '-C':
        name, equal, rest = value.partition('=')
        prefix = binding['target_dir'] + '/debug/incremental/'
        if equal and name == 'incremental' and rest.startswith(prefix):
            absolute(rest)
            namespace, slash, remainder = rest[len(prefix):].partition('/')
            need(namespace == binding['workspace_namespace'], 'unexpected incremental workspace namespace')
            return name + equal + '@target/debug/incremental/@workspace' + slash + remainder
        return name + equal + path(rest) if equal and name in ('incremental', 'linker', 'link-arg') else value
    if option == '-Z':
        name, equal, rest = value.partition('=')
        return name + equal + path(rest) if equal and name == 'temps-dir' else value
    raise ValueError('unknown normalizer option')


def normalize_argv(argv, binding):
    options = ('--out-dir', '--sysroot', '-o', '-L', '--extern', '--emit', '--remap-path-prefix', '-C', '-Z')
    result, index = [], 0
    while index < len(argv):
        argument = argv[index]
        need(not any(token in argument for token in ('@target', '@build', '@workspace')), 'reserved normalization token in literal argv')
        if argument in options:
            need(index + 1 < len(argv), 'missing option operand')
            operand = argv[index + 1]
            need(not any(token in operand for token in ('@target', '@build', '@workspace')), 'reserved normalization token in operand')
            result.extend((argument, normalize_operand(argument, operand, binding)))
            index += 2
            continue
        matched = False
        for option in options:
            prefix = option + '=' if option.startswith('--') else option
            if argument.startswith(prefix) and len(argument) > len(prefix):
                result.append(prefix + normalize_operand(option, argument[len(prefix):], binding))
                matched = True
                break
        if not matched:
            result.append(normalize_path(argument, binding)
                          if not argument.startswith('-') and argument.endswith(('.rs', '.rlink')) else argument)
        index += 1
    return result


def _text(data):
    need(type(data) is bytes and data.endswith(b'\n'), 'missing or truncated newline-terminated raw log')
    text = data.decode('utf-8', errors='strict')
    need('\x00' not in text and '\ufffd' not in text, 'ambiguous log encoding')
    return text


def _object(pairs):
    result = {}
    for key, value in pairs:
        need(key not in result, 'duplicate JSON object key')
        result[key] = value
    return result


def _commands(stderr, binding):
    commands = []
    for line in stderr.split('\n'):
        if not re.match(r'^\s*Running\b', line):
            continue
        match = re.fullmatch(r'\s*Running `(.*)`', line)
        need(match is not None, 'missing/truncated Running record')
        argv = shlex.split(match[1], comments=False, posix=True)
        need(argv and argv[0] == binding['compiler_path'], 'unexpected compiler executable or other Running command')
        names = [argument for argument in argv if argument == '--crate-name' or argument.startswith('--crate-name=')]
        need(len(names) == 1, 'missing or ambiguous crate-name')
        if names[0] == '--crate-name':
            position = argv.index('--crate-name')
            need(position + 1 < len(argv) and not argv[position + 1].startswith('-'), 'missing crate-name value')
        else:
            need(names[0] != '--crate-name=', 'empty crate-name value')
        inputs = [argument for argument in argv[1:] if not argument.startswith('-') and argument.endswith(('.rs', '.rlink'))]
        need(len(inputs) == 1, 'missing or ambiguous compiler input')
        commands.append({'argv': argv, 'input_kind': 'rlink' if inputs[0].endswith('.rlink') else 'source'})
    need(dict(Counter(row['input_kind'] for row in commands)) == STAGES[binding['workload']], 'missing/extra compiler invocation or stage')
    return commands


def _cstring(text, index):
    need(index < len(text) and text[index] == '"', 'expected complete trace string')
    index += 1
    value = bytearray()
    escapes = {'a': 7, 'b': 8, 'f': 12, 'n': 10, 'r': 13, 't': 9, 'v': 11, '\\': 92, '"': 34}
    while index < len(text) and text[index] != '"':
        character = text[index]
        index += 1
        if character != '\\':
            value.extend(character.encode('utf-8'))
            continue
        need(index < len(text), 'truncated trace escape')
        character = text[index]
        index += 1
        if character in escapes:
            value.append(escapes[character])
        elif character in '01234567':
            digits = character
            while index < len(text) and len(digits) < 3 and text[index] in '01234567':
                digits += text[index]
                index += 1
            need(int(digits, 8) <= 255, 'invalid trace octal escape')
            value.append(int(digits, 8))
        elif character == 'x':
            digits = text[index:index + 2]
            need(re.fullmatch('[0-9a-fA-F]{2}', digits), 'invalid trace hex escape')
            value.append(int(digits, 16))
            index += 2
        else:
            raise ValueError('unknown trace string escape')
    need(index < len(text), 'truncated trace string')
    need(0 not in value, 'NUL in exec argument')
    return value.decode('utf-8', errors='strict'), index + 1


def _exec(line):
    match = re.match(r'^(execve|execveat)\(', line)
    need(match is not None, 'unrecognized exec record')
    kind, index = match[1], match.end()
    if kind == 'execveat':
        directory = re.match(r'(?:AT_FDCWD|-?\d+),\s*', line[index:])
        need(directory is not None, 'ambiguous execveat directory')
        index += directory.end()
    path, index = _cstring(line, index)
    start = re.match(r',\s*\[', line[index:])
    need(start is not None, 'missing trace argv array')
    index += start.end()
    argv = []
    while index < len(line) and line[index] != ']':
        argument, index = _cstring(line, index)
        argv.append(argument)
        if index < len(line) and line[index] == ']':
            break
        separator = re.match(r',\s*', line[index:])
        need(separator is not None, 'truncated/ambiguous trace argv')
        index += separator.end()
    need(index < len(line) and line[index] == ']', 'unterminated trace argv')
    tail = r',\s*(?:0x[0-9a-fA-F]+|NULL)(?:\s*/\* \d+ vars \*/)?'
    if kind == 'execveat':
        tail += r',\s*(?:0|AT_EMPTY_PATH|AT_SYMLINK_NOFOLLOW)(?:\|(?:AT_EMPTY_PATH|AT_SYMLINK_NOFOLLOW))*'
    tail += r'\s*\)\s*=\s*(0|-1 [A-Z0-9_]+ \([^\n]*\))\s*'
    finish = re.fullmatch(tail, line[index + 1:])
    need(finish is not None, 'truncated/ambiguous exec result or environment')
    successful = finish[1] == '0'
    need(not successful or bool(path), 'successful execveat has no auditable path')
    return {'executable': path, 'argv': argv, 'successful': successful}


def trace_records(text):
    pending, records = {}, []
    for line in text.split('\n'):
        if not line:
            continue
        prefix = re.match(r'^(?:\[pid\s+(\d+)\]|(\d+))\s+(.*)$', line)
        pid, body = ((prefix[1] or prefix[2]), prefix[3]) if prefix else (None, line)
        if body.endswith('<unfinished ...>'):
            match = re.match(r'^(execve|execveat)\(', body)
            need(pid is not None and pid not in pending and match is not None, 'ambiguous unfinished exec record')
            pending[pid] = (match[1], body[:-len('<unfinished ...>')])
            continue
        resumed = re.match(r'^<\.\.\. (execve|execveat) resumed>(.*)$', body)
        if resumed:
            need(pid in pending and pending[pid][0] == resumed[1], 'orphan or mismatched exec resume')
            body = pending.pop(pid)[1] + resumed[2]
        else:
            need(pid not in pending, 'new record before unfinished exec completes')
        if body.startswith(('execve(', 'execveat(')):
            records.append(_exec(body))
        else:
            need(re.fullmatch(r'--- SIG(?:[A-Z0-9]+|RT_[0-9]+) \{.*\} ---|\+\+\+ exited with \d+ \+\+\+', body), 'unrecognized trace record')
    need(not pending, 'unfinished exec record remains')
    return records


def _multiset(commands):
    counts = Counter(canonical(row) for row in commands)
    return [{'invocation': json.loads(key), 'count': count} for key, count in sorted(counts.items())]


def signature(report, normalized=False):
    binding = report['binding']
    binding_check(binding)
    context = dict(binding)
    if normalized:
        context.update(target_dir='@target', build_dir='@build', workspace_namespace='@workspace')
    commands = [{'argv': normalize_argv(row['argv'], binding) if normalized else row['argv'],
                 'input_kind': row['input_kind']} for row in report['invocations']]
    return {'configured_context': context, 'invocations': _multiset(commands)}


def observe(stdout, stderr, binding, *, returncode, completion, raw_paths, trace=None):
    """Parse real raw bytes; context is configured provenance, not trace-observed cwd/env."""
    binding_check(binding)
    need(type(returncode) is int and returncode == 0, 'unsuccessful or missing returncode')
    need(completion in ('diagnostic-helper-success', 'sample-returncode'), 'unknown completion provenance')
    need(set(raw_paths) == {'stdout', 'stderr'} | ({'trace'} if trace is not None else set()), 'raw path fields differ')
    need(len(set(raw_paths.values())) == len(raw_paths), 'reused raw log path')
    raw = {}
    texts = {}
    for name, data in {'stdout': stdout, 'stderr': stderr, **({'trace': trace} if trace is not None else {})}.items():
        texts[name] = _text(data)
        raw[name] = {'path': absolute(raw_paths[name]), 'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}
    messages = [json.loads(line, object_pairs_hook=_object) for line in texts['stdout'].split('\n')[:-1]]
    need(messages and all(type(row) is dict for row in messages), 'invalid JSON build stream')
    finished = [row for row in messages if row.get('reason') == 'build-finished']
    need(finished == [{'reason': 'build-finished', 'success': True}] and messages[-1] == finished[0]
         and any(row.get('reason') == 'compiler-artifact' for row in messages), 'missing/truncated successful build stream')
    commands = _commands(texts['stderr'], binding)
    if trace is not None:
        records = trace_records(texts['trace'])
        compiler = [row for row in records if row['executable'] == binding['compiler_path']]
        need(all(row['successful'] for row in compiler), 'failed compiler exec attempt')
        need(all(not row['argv'] or row['argv'][0] != binding['compiler_path']
                 or row['executable'] == binding['compiler_path'] for row in records), 'compiler argv under another executable')
        need(Counter(canonical(row['argv']) for row in compiler)
             == Counter(canonical(row['argv']) for row in commands), 'verbose and traced full compiler argv differ')
    report = {'schema': 1, 'binding': dict(binding), 'binding_sha256': digest(binding),
              'returncode': returncode, 'completion': completion, 'raw': raw,
              'trace_argv_verified': trace is not None, 'invocation_count': len(commands),
              'invocations': commands}
    report['literal_argv_sha256'] = digest(signature(report))
    report['normalized_argv_sha256'] = digest(signature(report, True))
    return report


def _cell(value):
    need(type(value) is dict and set(value) == set(AXES), 'diagnostic cell fields differ')
    key = tuple(value[name] for name in AXES)
    need(key in CELLS, 'unknown diagnostic matrix cell')
    return key


def validate_diagnostics(cases, plan, *, provenance):
    """Seal all 16 cells; plan binds paths before diagnostics, namespaces come from reports."""
    need(set(provenance) == {'protocol_sha256', 'companion_source_sha256', 'diagnostic_manifest_path',
                            'diagnostic_manifest_sha256', 'diagnostic_outer_returncode', 'diagnostic_manifest_state'},
         'diagnostic provenance fields differ')
    need(provenance['protocol_sha256'] == PROTOCOL_SHA256
         and type(provenance['diagnostic_outer_returncode']) is int
         and provenance['diagnostic_outer_returncode'] == 0
         and provenance['diagnostic_manifest_state'] == 'complete', 'incomplete diagnostic provenance')
    absolute(provenance['diagnostic_manifest_path'])
    for key in ('companion_source_sha256', 'diagnostic_manifest_sha256'):
        need(isinstance(provenance[key], str) and re.fullmatch('[0-9a-f]{64}', provenance[key]), 'invalid diagnostic provenance digest')
    need(type(plan) is dict and set(plan) == {'schema', 'bindings', 'cells'} and plan['schema'] == 1, 'invalid prospective plan')
    need(type(plan['bindings']) is dict and len(plan['bindings']) == 4, 'expected four prospective target bindings')
    for binding in plan['bindings'].values():
        binding_check(binding, namespace=False)
    need(len({binding['target_dir'] for binding in plan['bindings'].values()}) == len(plan['bindings']),
         'physical target has multiple binding identities')
    need(dict(Counter(row['workload'] for row in plan['bindings'].values())) == {'test': 2, 'check': 2},
         'expected two targets per workflow')
    planned = {}
    for row in plan['cells']:
        need(set(row) == {'cell', 'binding_id'} and row['binding_id'] in plan['bindings'], 'invalid planned cell binding')
        cell = _cell(row['cell'])
        need(cell not in planned, 'duplicate planned matrix cell')
        need(plan['bindings'][row['binding_id']]['workload'] == cell[0], 'planned workflow differs')
        planned[cell] = row['binding_id']
    need(set(planned) == CELLS and set(planned.values()) == set(plan['bindings']), 'missing matrix cell or unused binding')
    need(dict(Counter(planned.values())) == {key: 4 for key in plan['bindings']}, 'expected four diagnostic cells per target')
    for workload, assignment in product(('test', 'check'), ('forward', 'reverse')):
        targets = []
        for variant in ('baseline', 'candidate'):
            target_id = planned[workload, assignment, 'native', variant]
            need(target_id == planned[workload, assignment, 'ir', variant], 'target assignment differs between execution modes')
            targets.append(plan['bindings'][target_id]['target_dir'])
        expected = ['base', 'cand'] if assignment == 'forward' else ['cand', 'base']
        need([PurePosixPath(path).name for path in targets] == expected
             and targets[0] != targets[1] and len(targets[0]) == len(targets[1]), 'invalid equal-length target assignment')
    seen, raw_paths, targets, normalized, receipts = set(), set(), {}, {}, []
    for case in cases:
        need(set(case) == {'cell', 'binding_id', 'report'}, 'diagnostic case fields differ')
        cell = _cell(case['cell'])
        need(cell not in seen, 'duplicate diagnostic matrix cell')
        seen.add(cell)
        target_id, report = case['binding_id'], case['report']
        need(target_id == planned[cell], 'diagnostic target assignment differs')
        need(report['schema'] == 1 and report['completion'] == 'diagnostic-helper-success'
             and type(report['returncode']) is int and report['returncode'] == 0 and report['trace_argv_verified'] is True
             and set(report['raw']) == {'stdout', 'stderr', 'trace'}, 'incomplete diagnostic observation')
        binding = report['binding']
        need({key: value for key, value in binding.items() if key != 'workspace_namespace'}
             == plan['bindings'][target_id], 'diagnostic configured binding differs')
        literal, common = signature(report), signature(report, True)
        need(report['binding_sha256'] == digest(binding)
             and report['literal_argv_sha256'] == digest(literal)
             and report['normalized_argv_sha256'] == digest(common)
             and report['invocation_count'] == len(report['invocations'])
             == sum(STAGES[cell[0]].values()), 'diagnostic report digest/count differs')
        paths = {value['path'] for value in report['raw'].values()}
        need(len(paths) == 3 and not paths.intersection(raw_paths), 'diagnostic raw paths reused across cells')
        raw_paths.update(paths)
        if target_id in targets:
            need(targets[target_id]['literal_signature'] == literal, 'per-target literal argv differs')
        else:
            targets[target_id] = {'binding': binding, 'literal_signature': literal,
                                  'literal_argv_sha256': digest(literal), 'normalized_argv_sha256': digest(common)}
        if cell[0] in normalized:
            need(normalized[cell[0]] == common, 'compiler argv/context differs beyond bound path substitutions')
        else:
            normalized[cell[0]] = common
        receipts.append({'cell': case['cell'], 'binding_id': target_id, 'report_sha256': digest(report),
                         'raw': report['raw'], **{key: report[key] for key in (
                             'binding_sha256', 'invocation_count', 'literal_argv_sha256', 'normalized_argv_sha256')}})
    need(seen == CELLS, 'missing diagnostic matrix cell')
    return {'schema': 1, 'state': 'sealed-full-argv-expectations', 'prospective_plan_sha256': digest(plan),
            'provenance': dict(provenance), 'normalized_workflows': normalized,
            'diagnostic_cells': sorted(receipts, key=lambda row: _cell(row['cell'])), 'targets': targets}


def validate_sample(report, expectations, target_id):
    need(expectations['schema'] == 1 and expectations['state'] == 'sealed-full-argv-expectations'
         and len(expectations['diagnostic_cells']) == 16
         and {_cell(row['cell']) for row in expectations['diagnostic_cells']} == CELLS,
         'missing complete diagnostic expectation seal')
    need(report['completion'] == 'sample-returncode' and type(report['returncode']) is int
         and report['returncode'] == 0 and report['trace_argv_verified'] is False
         and set(report['raw']) == {'stdout', 'stderr'}, 'incomplete sample observation')
    expected = expectations['targets'][target_id]
    literal = signature(report)
    need(report['binding'] == expected['binding'] and literal == expected['literal_signature']
         and digest(literal) == report['literal_argv_sha256'] == expected['literal_argv_sha256']
         and digest(signature(report, True)) == report['normalized_argv_sha256'] == expected['normalized_argv_sha256']
         and report['binding_sha256'] == digest(report['binding'])
         and report['invocation_count'] == len(report['invocations'])
         == sum(STAGES[report['binding']['workload']].values()), 'sample differs from exact per-target full argv')
    return {'status': 'passed', 'report_sha256': digest(report), 'binding_sha256': report['binding_sha256'],
            'invocation_count': report['invocation_count'], 'literal_argv_sha256': report['literal_argv_sha256'],
            'normalized_argv_sha256': report['normalized_argv_sha256'],
            'raw': report['raw']}
