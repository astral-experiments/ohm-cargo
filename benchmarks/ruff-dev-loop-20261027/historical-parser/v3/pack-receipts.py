from pathlib import Path
import collections,gzip,hashlib,json
p=Path(__file__).resolve().parent;root=p.parents[1];raw=root/'historical-confirmation-v3-raw';args={};records={}
def g(f,j):f.write_bytes(gzip.compress((json.dumps(j,sort_keys=True,separators=(',',':'))+'\n').encode(),mtime=0))
for f in sorted(raw.glob('*/receipt.json')):
    rec=f.parent;j=json.loads(f.read_bytes());units=[]
    for l in (rec/'stdout').read_bytes().splitlines():
        x=json.loads(l)
        if x['reason']=='compiler-artifact':units.append([x['package_id'],x['target']['name'],x['target']['kind'],x['fresh'],[Path(y).name for y in x['filenames']]])
    assert len(units)==j['units']
    unit_key=hashlib.sha256(json.dumps(sorted(units,key=str),separators=(',',':')).encode()).hexdigest()
    unit_ref='units-'+unit_key
    if unit_ref not in args:args[unit_ref]=sorted(units,key=str)
    aa={}
    for a in sorted(rec.glob('rustc.*.argv')):
        blob=a.read_bytes();h=hashlib.sha256(blob).hexdigest();args.setdefault(h,[b.decode() for b in blob.split(b'\0') if b]);aa[a.name]=h
    rr={k:j[k]for k in ('command','mode','arm','phase','elapsed_ns','units','dirty','rustcs','parser_api','executables','compiler','base','edit','patch_sha256')};rr.update({'unit_graph':unit_ref,'argv_by_name':aa,'elf_sections':json.loads((rec/'elf-sections.json').read_bytes()),'elf_symbols':json.loads((rec/'elf-symbols.json').read_bytes()),'cli_behavior':json.loads((rec/'semantic.json').read_bytes()),'raw_stdout_sha256':hashlib.sha256((rec/'stdout').read_bytes()).hexdigest(),'raw_stderr_sha256':hashlib.sha256((rec/'stderr').read_bytes()).hexdigest()});records[rec.name]=rr
g(p/'command-arguments.json.gz',args);g(p/'command-receipts.json.gz',records);print(len(records),'native or fresh commands with full inputs and qualification outputs')
