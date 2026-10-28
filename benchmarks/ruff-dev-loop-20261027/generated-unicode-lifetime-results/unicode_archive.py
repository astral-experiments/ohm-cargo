"""Archive one observed native CLI and the typed restored generator program before releasing the experiment's isolated mount."""
from pathlib import Path
import gzip, os, shutil, sys
sys.path.insert(0,str(Path(__file__).resolve().parent));from basic import *
src=q/'unicode-lifetime-v1';z=json.loads((src/'restored/result.json').read_bytes());assert z['source']==json.loads((q/'ops/unicode-plan.json').read_bytes())['original']
gen=json.loads((src/'restored/jobs.json').read_bytes());script,=[j for j in gen if j['kind']=='wild' and j['name']=='build_script_build'];wild,=[j for j in gen if j['kind']=='wild'and j['name']=='ruff']
frozen=src/'private-final-elves';frozen.mkdir();eg=guard();rows=[]
for name,path,expected in [('ruff',Path(wild['out']),z['cli_elf']),('build-script',Path(script['out']),script['out_digest'][1])]:
    assert sha(path)==expected
    fp=frozen/(name+'.gz')
    assert shutil.disk_usage(frozen).free>25*2**30+(200<<20)
    with path.open('rb')as a,fp.open('wb')as raw,gzip.GzipFile(filename='',mode='wb',compresslevel=2,fileobj=raw,mtime=0)as out:shutil.copyfileobj(a,out,1<<20)
    with gzip.open(fp,'rb')as g:assert hashlib.file_digest(g,'sha256').hexdigest()==expected
    rows.append(dict(name=name,full_sha=expected,full_bytes=path.stat().st_size,gz_sha=sha(fp),gz_bytes=fp.stat().st_size))
put(frozen/'verified.json',{'source':z['source'],'records':rows,'before':eg,'after':guard()})
