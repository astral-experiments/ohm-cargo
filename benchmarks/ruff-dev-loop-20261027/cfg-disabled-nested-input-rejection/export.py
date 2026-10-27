"""Project the actual A, B, C H1 ELF and linker outcomes from the checked native probe."""
from pathlib import Path
import ast, hashlib, json, re, socket
assert socket.gethostname()=='charlie-ohm-relink-perf-1024'
q=Path('/dev/shm/ohm-stdlib-native-scout-20261027');run=q/'root-nested-script-v1'
def sha(p):
    with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def read(p):return json.loads(p.read_bytes())
def identity(path):
    p=Path(path)
    if p.name=='libutil.a' or p.name=='librt.a':return str(p)
    return p.name
assert read(run/'returncodes.json')=={a:0 for a in ('baseline','a9b','a9c')}
result={'fixture_sha256':sha(run/'probe.py'),'base_fixture_sha256':sha(q/'tiny-guards-233a9.py'),'arms':{}}
for arm in ('baseline','a9b','a9c'):
    d=q/('tiny-'+arm+'-nested-root-v1');info=read(d/'result.json')
    sr={k:info[k] for k in ('arm','cargo','rust','wild','system_script_sha','ordinary_fallback_sha','added_object_sha')};sr['phases']={};result['arms'][arm]=sr
    for name,rec in info['samples'].items():
        phase=d/name
        j={k:rec.get(k) for k in ('rc','elf','fixed','full','marker','rustcs','tests','wild')};sr['phases'][name]=j
        j['physical']=[]
        for p in sorted(phase.glob('exec.*')):
            for line in p.read_text(errors='replace').splitlines():
                m=re.match(r'execve\(("(?:[^"\\]|\\.)*"), (\[.*\]), (?:0x[0-9a-f]+|NULL).*\)\s+= 0$',line)
                if not m:continue
                img=Path(ast.literal_eval(m[1]));av=ast.literal_eval(m[2])
                if img.name=='rustc' and '--crate-name' in av:
                    cr=av[av.index('--crate-name')+1]
                    if cr in ('_','__','___'):continue
                    role='rustc'
                elif img.name in ('collect2','cc','ld.bfd') and '-o' in av:
                    output=Path(av[av.index('-o')+1]).name
                    if not output.startswith('api-'):continue
                    cr='api';role='Wild' if (img.name=='ld.bfd' and img.parent.name=='wild-ld') else img.name
                else:continue
                j['physical'].append({'process':p.name,'role':role,'crate':cr,'file_sha256':sha(p),'exec_record_sha256':hashlib.sha256(line.encode()).hexdigest(),'one_worker':'--threads=1' in av})
        assert sorted(z['crate'] for z in j['physical'] if z['role']=='rustc')==sorted(j['rustcs'])
        assert len([z for z in j['physical'] if z['role']=='Wild'])==sum(n.startswith('api-') for n in j['wild'])
        j['stderr_digest']=sha(phase/'stderr');j['cargo_messages_digest']=sha(phase/'stdout')
        errors=[]
        for line in (phase/'stdout').read_text().splitlines():
            dmsg=json.loads(line)
            if dmsg.get('reason')!='compiler-message':continue
            msg=dmsg['message'];lines=(msg.get('rendered','') or '').splitlines()
            hits=[l.strip() for l in lines if '__ohm_nested_input_no_such_file__' in l]
            if hits:errors.extend([{'level':msg['level'],'message':msg['message'],'evidence':hits}])
        j['unresolved_input_errors']=errors
        proof=rec.get('proof')
        if proof:
            j['native_certificate']={k:proof[k] for k in ('source','input_digest','fixed_worker','elf')}
            j['resolved_compatibility_archives']=[identity(p) for p in rec['recorded_rt_order']]
            j['includes_sdk_directory']=any(p.endswith('rustlib/x86_64-unknown-linux-gnu/lib') for p in rec['watched_directories'])
            j['includes_nested_directory']=any(p.endswith('rustlib/x86_64-unknown-linux-gnu/lib/x86_64-linux-gnu') for p in rec['watched_directories'])
print(json.dumps(result,sort_keys=True,indent=2))
