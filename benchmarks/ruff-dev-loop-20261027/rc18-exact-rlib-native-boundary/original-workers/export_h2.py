import hashlib, json, os, tarfile, gzip, tempfile, subprocess, sys
from pathlib import Path
root=Path('/mnt/devbox-scratch/dev-user/ohm-native-cargo-raw-boundary-r2-20261028')
get=lambda p: json.loads(p.read_bytes())
k=lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
private=root/'evidence-export';private.mkdir(exist_ok=True)
donors={}
for i in (41,83):
    tmp=private/str(i);tmp.mkdir(exist_ok=True)
    (tmp/'native.c').write_text(f'int atoi(const char *p) {{ return {i}; }}\n')
    subprocess.run(['cc','-fPIC','-c','native.c','-o','native.o'],cwd=tmp,check=True)
    subprocess.run(['ar','rcsD','libutil.a','native.o'],cwd=tmp,check=True)
    donors[i]=k(tmp/'libutil.a')
ledger={}
for name in ('v2','v3','v4'):
    assert get(root/(name+'.terminal.json'))['status']==0
    d=root/name/'reports';j=get(d/'all.json');assert get(d/'verified.json')['pass']
    if name=='v4':
        assert all(donors[i]==j[phase]['files']['actual_out_dir_libutil']['sha256'] for i,phase in [(41,'same-provider-baseline'),(83,'earlier-provider')])
    for f in sorted(d.rglob('exec.*')):
        ledger[str(f.relative_to(root))]=k(f)
(private/'raw-trace-sha256.json').write_text(json.dumps(ledger,sort_keys=True)+'\n')
members=list(private.rglob('*'))
for name in ('v1','v2','v3','v4'):
    body=root/name; d=body/'reports'
    members += [root/(name+suffix) for suffix in ('.stdout','.stderr','.terminal.json')]
    members += list((body/'source').rglob('*'))
    members += [d/'all.json']
    if name=='v1':continue
    members += [p for p in d.rglob('*') if p.is_file() and not p.name.startswith('exec.')]
    if name=='v4':
        members += [body/'target/debug/reader',body/'external/libutil.a']
        # Independently retain raw strace lines surrounding the exact default library selection.
        for label in ('earlier-provider','repeat','removed-provider','same-size-time-native'):
            stats=get(d/label/'native-observations.json')['lookups']
            for ident in {r['tid'] for r in stats if '/search/' in r['text'] and '/libutil.a' in r['text']}:
                members.append(d/label/('exec.'+ident))
members=[p for p in sorted(set(members)) if p.is_file()]
assert all(p.is_relative_to(root) and not p.is_symlink() for p in members)
with tarfile.open(fileobj=sys.stdout.buffer,mode='w|gz',compresslevel=9) as out:
    for p in members:out.add(p,arcname=str(p.relative_to(root)),recursive=False)
