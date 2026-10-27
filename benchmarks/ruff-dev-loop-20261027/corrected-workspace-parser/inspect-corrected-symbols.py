"""Identify the proc-macro dynamic symbol difference between the two cold ELF receipts."""
import hashlib
import json
from pathlib import Path
import struct

root = Path('/mnt/devbox-scratch/dev-user/ohm-whole-skips-20261027')
reference = root/'revision-native-66815c41574c-elf-reference'
key = 'ohm-whole-skips-20261027/native-target/debug/libruff_macros.so'
result = {}

def symbols(binary):
    sectionoff, = struct.unpack_from('<Q',binary,40)
    size,count,shstr = struct.unpack_from('<HHH',binary,58)
    secs=[struct.unpack_from('<IIQQQQIIQQ',binary,sectionoff+i*size) for i in range(count)]
    def string(table,offset):
        start=secs[table][4]+offset
        return binary[start:binary.index(b'\0',start)].decode()
    names=[string(shstr,s[0]) for s in secs]
    tables={}
    for name in ['.dynsym','.symtab']:
        section=secs[names.index(name)]
        entries=[]
        for i in range(section[4], section[4]+section[5], section[9]):
            nameoff,info,other,index,value,length=struct.unpack_from('<IBBHQQ',binary,i)
            entries.append(dict(name=string(section[6],nameoff),info=info,other=other,section=names[index] if index < len(names) else str(index),value=value,size=length))
        tables[name]=entries
    return tables

for arm,store in [('parent',root/'reference-parser-v3/parent-cold-target'),('candidate',reference/'candidate-cold-target')]:
    expected=json.loads((reference/(arm+'-cold-build-edited.json')).read_bytes())['products'][key]
    f=store/'debug/libruff_macros.so'
    paths=[f] if f.is_file() else list(store.rglob('libruff_macros-0df74ae72023ec23.so'))
    for path in paths:
        data=path.read_bytes(); actual=hashlib.sha256(data).hexdigest()
        if actual==expected['raw_sha256']:break
    else:raise AssertionError((arm,paths,expected['raw_sha256']))
    result[arm]=dict(sha256=actual,rustc_section_size=expected['sections']['.rustc']['size'],tables=symbols(data))
a=result['parent'].pop('tables');b=result['candidate'].pop('tables'); result['tables']={}
for name in a:
    assert len(a[name])==len(b[name]); changes=[]
    for i,(p,c) in enumerate(zip(a[name],b[name])):
        if p!=c:changes.append(dict(index=i,parent=p,candidate=c))
    result['tables'][name]=dict(entries=len(a[name]),changed=changes)
print(json.dumps(result,sort_keys=True,indent=2))
