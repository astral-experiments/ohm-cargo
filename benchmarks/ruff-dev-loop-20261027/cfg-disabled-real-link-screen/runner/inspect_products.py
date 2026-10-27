"""Native hashes, listing, behavior and actual foreign Rust field-access witnesses."""
from shared import *
from elf import elf
from roster import audit_json
from processes import parsed
import subprocess
TESTS={'ruff_wasm','ty_wasm'}
CODES={'parser':['Cannot mix t-string literals with string or bytes literals','Bytes literal cannot be mixed with non-bytes literals']}
def cli(ruff,desc,edited):
    mixed=b"t'first' b'second'\n";stdlib=b'from collections import ChainMap\nfrom weakref import WeakSet\n\ndef f(a=ChainMap(), b=WeakSet()):\n    pass\n'
    res={}
    for label,args,data in [('parser',['--target-version','py314'],mixed),('stdlib',['--select','B006,B008','--stdin-filename','stdlib_case.py'],stdlib)]:
        ret=subprocess.run([str(ruff),'check','--isolated','--no-cache','--output-format','json',*args,'-'],cwd=WT,env=env(),input=data,capture_output=True)
        need(ret.returncode==1 and not ret.stderr,('Ruff CLI',ret.returncode,ret.stderr[:300]))
        diag=json.loads(ret.stdout);res[label]=[{k:x[k] for k in ('code','message','location','end_location')} for x in diag]
    need([r['message'] for r in res['parser']]==[CODES['parser'][int(desc=='parser' and edited)]],('parser behavior',res))
    need([(r['location']['row'],r['code']) for r in res['stdlib']]==[(4,'B008' if desc=='stdlib' and edited else 'B006')]*2,('stdlib behavior',res))
    return res
def library(rows,edition,out):
    unit,=[r for r in rows if r.get('reason')=='compiler-artifact' and not r['profile']['test'] and r['target']['name']=='ty_wasm' and set(r['target']['crate_types'])=={'rlib','cdylib'}]
    meta,=[p for p in unit['filenames'] if p.endswith('.rmeta')]
    directories=sorted({str(Path(p).parent) for a in rows if a.get('reason')=='compiler-artifact' for p in a['filenames'] if p.endswith(('.rlib','.rmeta','.so'))})
    result={}
    for name,src in [('position',b'pub fn position(h:&ty_wasm::InlayHint)->&ty_wasm::Position { &h.position }\n'),('text_edits',b'pub fn edits(h:&ty_wasm::InlayHint)->&Vec<ty_wasm::TextEdit> { &h.text_edits }\n')]:
        cmd=['rustc','+ohm','--crate-type=rlib','--edition=2024','--emit=metadata','--crate-name','caller_'+name,'--error-format=json','--extern','ty_wasm='+meta,'-o',str(out/(name+'.rmeta')),'-']
        for d in directories:cmd+=['-L','dependency='+d]
        ret=subprocess.run(cmd,input=src,stdout=subprocess.PIPE,stderr=subprocess.PIPE,env=env(),cwd=WT)
        errors=[j for line in ret.stderr.splitlines() if (j:=json.loads(line)).get('level')=='error' and j.get('code')]
        codes=[j['code']['code'] for j in errors];actual={'returncode':ret.returncode,'codes':codes,'message':[j['message'] for j in errors]}
        (out/(name+'.stderr')).write_bytes(ret.stderr)
        expect=edition and name=='text_edits';need((ret.returncode,codes)==((1,['E0609']) if expect else (0,[])),('ordinary Rust caller',name,actual,ret.stderr[:700]))
        result[name]=actual
    return result
def collect(out,edit,edited,arm,rich,trace):
    j=audit_json(out/'stdout','test')
    rows=[json.loads(line) for line in (out/'stdout').read_bytes().splitlines() if line]
    arts=[r for r in rows if r['reason']=='compiler-artifact']
    ruff,={r['executable'] for r in arts if not r['profile']['test'] and r['target']['name']=='ruff' and r['target']['kind']==['bin'] and r['executable']}
    api={}
    for a in arts:
        if a['target']['name']!='api' or a['target']['kind']!=['test']:continue
        pkg=Path(a['manifest_path']).parent.name;exe=Path(a['executable']);need(pkg in TESTS and exe.is_file() and not exe.is_symlink(),'actual API path')
        listing=subprocess.run([str(exe),'--list'],capture_output=True,env=env(),cwd=WT)
        need(listing.returncode==0 and not listing.stderr and listing.stdout.strip()==b'0 tests, 0 benchmarks',('test list',pkg,listing.stdout))
        p=exe.with_suffix('.rlink-cache.json');raw=load(p).get('disabled_test') if p.is_file() else None
        if arm in 'BC':need(isinstance(raw,dict) and type(raw['fixed_worker']) is bool and len(raw['files'])>=1,('missing authored disabled certificate',pkg,p))
        else:need(raw is None,('baseline certified candidate',pkg))
        api[pkg]={'file':str(exe),'raw':sha(exe),'certificate_sha256':sha(p) if raw else None,'fixed_worker':raw['fixed_worker'] if raw else None,'native_inputs':len(raw['files']) if raw else 0,'test_list':listing.stdout.decode().strip(),'elf_witness':elf(exe) if rich else None}
    need(api.keys()==TESTS,'wrong integration files')
    result={'units':j['units'],'executables':len(j['executables']),'elf_count':len(j['elf']),'dirty':j['dirty'],'roster':j['roster_sha256'],'messages':j['message_sha256'],'api':api,'cli':cli(ruff,edit,edited)}
    if rich:
        result['elf']={n:elf(Path(n)) for n in j['elf']}
        result['rust_caller']=library(rows,edit=='wasm-only' and edited,out)
    if trace:result['processes']=parsed(out,j)
    return result
