import hashlib,json,os,re,struct,sys,zlib
from pathlib import Path
p=Path(sys.argv[1]);d=p/'spaced-dirty-attribution-20261028';canonical=p/'member-build-matched-canonical-v1'
def sha(b):return hashlib.sha256(b).hexdigest()
def sections(path):
    with path.open('rb') as fi:
        b=fi.read()
    assert b[:6]==b'\x7fELF\x02\x01'
    off=struct.unpack_from('<Q',b,40)[0];shsize,num,idx=struct.unpack_from('<HHH',b,58)
    def sh(i):
        v=struct.unpack_from('<IIQQQQIIQQ',b,off+i*shsize);return v
    s=sh(idx);names=b[s[4]:s[4]+s[5]]
    out={}
    for i in range(num):
        z=sh(i);name=names[z[0]:].split(b'\0',1)[0].decode(errors='replace')
        if name in {'.text','.rodata','.eh_frame','.symtab','.dynsym','.note.gnu.build-id'}:out[name]=[z[5],sha(b[z[4]:z[4]+z[5]])]
    return {'raw':sha(b),'sections':out}
rows={}
for i in ('B','C'):
    f=d/('observations/03-'+i+'/edit/life.json');life=json.loads(f.read_bytes())
    r=next(x for x in life['records'] if Path(x['exe']).name=='build_script_build')
    raw=Path(r['exe']);state=d/'states'/(i+'wasm-ty_wasm')/'state'
    for n,ln in [('target','ruff target'),('shared','shared')]:
        if raw.is_relative_to(canonical/ln):file=state/n/raw.relative_to(canonical/ln);break
    else:raise ValueError(raw)
    rows[i]={'physical':str(file),'base':str(raw),'elf':sections(file)}
print(json.dumps(rows,sort_keys=True))
