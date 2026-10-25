import re

def normalized_compiler(rows):
    result = []
    for row in rows:
        env = dict(item.split('=', 1) for item in row['environment'])
        assert len(env) == len(row['environment'])
        omitted = {key: env.pop(key) for key in ('CARGO_MAKEFLAGS', 'MAKEFLAGS', 'MFLAGS') if key in env}
        assert set(omitted) == {'CARGO_MAKEFLAGS'}
        result.append({'argv': row['argv'], 'environment': env,
                       'environment_rows': [item for item in row['environment']
                                            if item.split('=', 1)[0] not in omitted]})
    return result

def compile_packages(stderr):
    return sorted(set(re.findall(r"^\s*(?:Checking|Compiling)\s+([^\s]+)\s+v[^\s]+", stderr, re.MULTILINE)))

def diagnostics(text):
    text = re.sub(r'^==\d+==.*\n?', '', text, flags=re.M)
    return re.sub(r'^\s*Finished .* in .*$', '', text, flags=re.M)

