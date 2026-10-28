"""Validate the genuine generated sources, native builds, full emitted metadata and ordinary readers."""
from collections import Counter
from pathlib import Path
import ast,gzip,hashlib,json,re,struct,tarfile
root=Path(__file__).resolve().parent
hash_bytes=lambda b:hashlib.sha256(b).hexdigest()
read=lambda n:(root/n).read_bytes()
ledger=json.loads(read("records.json"))
archives=json.loads(gzip.decompress(read("native-members.json.gz")))
objects={}
for path in sorted(root.glob("contents-*.tar.gz")):
    with tarfile.open(path) as t:
        for entry in t:
            b=t.extractfile(entry).read()
            assert entry.isfile() and hash_bytes(b)==entry.name and entry.name not in objects
            objects[entry.name]=b
def data(n):return objects[ledger[n]['portable']]
def rec(n):return json.loads(data(n))
def md(b):
    assert b[:6]==bytes.fromhex('7f454c460201')
    off=struct.unpack_from('<Q',b,40)[0];w,n,si=struct.unpack_from('<HHH',b,58)
    sections=[struct.unpack_from('<IIQQQQIIQQ',b,off+w*i)for i in range(n)]
    sy=sections[si];ss=b[sy[4]:sy[4]+sy[5]]
    h,=[s for s in sections if ss[s[0]:ss.index(0,s[0])]==b'.rmeta']
    return b[h[4]:h[4]+h[5]]
for n,l in ledger.items():
    if 'portable' in l:
        b=data(n)
        if l['sha']==l['portable']:assert len(b)==l['size']
        else:assert b'compiler-registry.invalid' in b
    else:
        a=archives[l['sha']];assert a['private_strings'] and a['whole']==[l['size'],l['sha']]
        size,h=a['native_metadata_member'];elf=objects[h];assert len(elf)==size
        assert md(elf)==data('raw/'+a['standalone_metadata'])
        assert [m[1:]for m in a['ordered_archive_members']if m[0]=='lib.rmeta']==[[size,h]]
plan=json.loads(read('unicode-plan.json'));assert hash_bytes(read('unicode.patch'))==plan['patch'] and hash_bytes(read('unicode-reader.rs'))==plan['caller']
init,edit,restore='original','edited','restored';ns=plan['order']
assert rec('complete.json')['stages']==ns and rec('bound.json')['verified']==plan['release']
key=lambda t,n:t+'/'+n
def typed(t):
    ev=[json.loads(l)for l in data(t+'/cargo.stdout').splitlines()];assert ev[-1]=={'reason':'build-finished','success':True}
    return ev
wanted=Counter([('full','unicode_names2_generator'),('full','build_script_build'),('wild','build_script_build'),('script','build_script_build'),('full','unicode_names2'),('partial','ruff'),('wild','ruff')])
def inspect_jobs(tag,needed):
    jobs=rec(tag+'/jobs.json')
    assert Counter((v['kind'],v['name'])for v in jobs)==needed
    for v in jobs:
        name=tag+'/trace/'+v['pid'];assert ledger[name]['sha']==v['raw_sha'] and v['exit']==0
        raw=data(name);assert b'+++ exited with 0 +++'in raw
        argv=[ast.literal_eval(x.decode())for x in re.findall(rb'execve\("(?:[^"\\]|\\.)*",\s*(\[.*?\]),\s*(?:0x[\da-f]+|NULL)',raw)]
        assert v['args'] in argv
        if v['kind'] in ('full','partial'):
            a=v['args'];partial=any(k.startswith('-Zlink-only')or (k=='-Z'and i+1<len(a)and a[i+1].split('=')[0]=='link-only')for i,k in enumerate(a))
            assert partial==(v['kind']=='partial')
        if v['kind']=='wild' and v['name']=='ruff':
            paths=v['explicit_files_post'];assert len(paths)==307 and [Path(n).name for n,d in paths if d is None]==['symbols.o']
            assert sum(n.endswith('.rlib')and 'libunicode_names2-' in Path(n).name for n,_ in paths)==1
        if v['kind']=='wild' and v['name']=='build_script_build': assert len(v['explicit_files_post'])==50 and sum(x[1]is None for x in v['explicit_files_post'])==13
    return jobs
sets={};gens={};native={}
for tag in ns:
    s=rec(key(tag,'result.json'));sets[tag]=s
    e=typed(tag);u=[v for v in e if v['reason']=='compiler-artifact'];assert len(u)==s['units']==373 and sum(v['fresh']for v in u)==s['fresh']
    assert s['fresh']==(354 if tag in (edit,restore) else 373)
    j=inspect_jobs(tag,wanted if tag in (edit,restore) else Counter());assert Counter(v['kind']for v in j)==s['counts']
    a=rec(key(tag,'generated.json'));g=a['files'];gens[tag]={n:data('raw/'+v['sha'])for n,v in g.items()};assert all(len(gens[tag][n])==v['bytes']for n,v in g.items())
    typed_script,=[v for v in e if v['reason']=='build-script-executed'and v['package_id'].split('#')[0].endswith('/ruff_unicode_names2')]
    assert a['typed']==typed_script and all(not a['typed'][k]for k in ('cfgs','env','linked_libs','linked_paths'))
    native[tag]=rec(key(tag,'unicode-native.json'));c=rec(key(tag,'controls.json'))
    assert c['cli']['good']['run']['status']==0 and not c['cli']['good']['diagnostics']
    dx,=c['cli']['bad']['diagnostics'];assert (dx['code'],dx['message'],dx['location'])==('invalid-syntax','Got unexpected unicode',{'row':1,'column':9})
    if 'repeat' not in tag:
        o=c['ordinary_caller'];assert o['compile']['status']==o['native']['status']==0 and o['negative_args']['status']==1
        out=data(tag+'/reader.stdout')
        assert all(val in out for val in (b'LATIN CAPITAL LETTER A',b'SNOWMAN',b'CRAB',b'LF alias and absent spelling checked'))
        dx,=[v for b in data(tag+'/reader-error.stderr').splitlines()for v in[json.loads(b)] if(v.get('code')or{}).get('code')=='E0061']
        assert any(s['file_name'].endswith('/ruff_unicode_names2/src/lib.rs')and s['line_start']==218 and s['column_start']==8 for c in dx['children']for s in c['spans'])
assert len({v['cli_elf']for v in sets.values()})==1
for n,count in [('generated.rs',8),('generated_phf.rs',2),('generated_alias.rs',0)]:
    a,b,c=[gens[v][n]for v in(init,edit,restore)]
    assert a==c and len(b)-len(a)==count*8
    # Replace the spelling only in top-level generated static declaration prefixes. All table values remain bitwise equal.
    fixed,ct=re.subn(rb"(?m)^(pub static [a-zA-Z_0-9]+: &)'static (?=(?:\[|str))",rb"\1",b)
    assert fixed==a and ct==count,(n,ct)
for pkg,expected in [('unicode_names2',13),('unicode_names2_generator',173)]:
    a,b,c=[native[v][pkg]for v in(init,edit,restore)]
    ars=[archives[v['rlib']['sha']]for v in(a,b,c)]
    m=[[v for v in item['ordered_archive_members']if v[0].endswith('.o')]for item in ars]
    assert all(len(x)==expected for x in m)
    assert all(x[0]!=y[0]for x,y in zip(m[0],m[1])) and all(x[2]==y[2]for x,y in zip(m[0],m[2]))
    assert sum(x[2]==y[2]for x,y in zip(m[0],m[1]))==(13 if pkg=='unicode_names2'else 170)
    assert a['rmeta']['sha']==c['rmeta']['sha']!=b['rmeta']['sha'] and a['hash']==c['hash']
    assert (a['hash'][-1]==b['hash'][-1])==(pkg=='unicode_names2')
    sx=[u['index_by_symbol_and_member_ordinal']for u in ars]
    assert len(sx[0])==(37 if pkg=='unicode_names2'else 1472)
    assert sx[0]==sx[2] and ((sx[0]==sx[1])==(pkg=='unicode_names2'))
    assert ars[0]['raw_symbol_index']!=ars[1]['raw_symbol_index']
dd='run-output-supplement/'
assert rec(dd+'complete.json')['full_additional_cargo_commands']==2
seen=[]
for tag in (init,edit,restore):
    v=rec(dd+tag+'/result.json');seen.append(v)
    for k,w in v['run_files'].items():
        b=data(dd+tag+'/script.'+k);assert [len(b),hash_bytes(b)]==[w['bytes'],w['sha']]
        if k=='stdout':assert b'cargo:rerun-if-changed=build.rs' in b and b'cargo:rerun-if-changed=data/' in b
    if tag!=init:inspect_jobs(dd+tag,wanted)
    assert v['cli']['sha']==sets[tag]['cli_elf'] and len(v['cli']['objects'])==22 and v['typed_generated']==rec(tag+'/generated.json')['files']
a,b,c=seen
assert a['cli']==b['cli']==c['cli'] and a['run_files']==b['run_files']==c['run_files']
assert a['script']['sha']==c['script']['sha']!=b['script']['sha'] and a['script']['sections']['.text']!=b['script']['sections']['.text'] and a['script']['sections']['.rodata']!=b['script']['sections']['.rodata']
if (root/'SHA256SUMS').exists():
    for l in read('SHA256SUMS').decode().splitlines():
        dg,n=l.split('  ',1);assert dg==hash_bytes(read(n)),n
print(f"{len(ledger)} records, {len(objects)} portable objects, six full crate archives bound and all native metadata members verified")
print("6 first-sequence native CLI builds and 2 supplemental builds, 373 units each. Two generated files change in exactly 10 explicit static positions. Native and diagnostics controls agree.")
