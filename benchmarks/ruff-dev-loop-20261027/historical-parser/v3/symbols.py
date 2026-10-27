"""Decode final ELF64 static symbols together with their referenced strings and section identities."""
from pathlib import Path
import hashlib,json,mmap,struct
def decompose(elf):
    with Path(elf).open('rb') as fd,mmap.mmap(fd.fileno(),0,access=mmap.ACCESS_READ) as image:
        assert image[:6]==b'\x7fELF\x02\x01'
        offset,=struct.unpack_from('<Q',image,40);stride,count,names_index=struct.unpack_from('<HHH',image,58)
        table=[struct.unpack_from('<IIQQQQIIQQ',image,offset+i*stride) for i in range(count)]
        def data(section):
            return image[section[4]:section[4]+section[5]]
        def at(pool,index):
            end=pool.find(b'\0',index);assert 0<=index< len(pool) and end>=index
            return pool[index:end].decode('utf-8')
        names=data(table[names_index]);sections=[at(names,t[0]) for t in table]
        ix=sections.index('.symtab');symtab=table[ix];symbols=data(symtab);strings=data(table[symtab[6]])
        assert symtab[1]==2 and symtab[9]==24 and sections[symtab[6]]=='.strtab'
        # A consumer containing relocations indexed into this table would also need the order.
        # All relocations in this final executable use the dynamic table, which stays byte-exact.
        users=[sections[i] for i,section in enumerate(table) if section[6]==ix]
        assert not users,users
        entries=[]
        for name,info,other,section,value,size in struct.iter_unpack('<IBBHQQ',symbols):
            sec=sections[section] if section<len(sections) else section
            entries.append((at(strings,name),info,other,sec,value,size))
        enc=lambda rows:json.dumps(rows,separators=(',',':'),ensure_ascii=False).encode()
        canon=sorted(entries,key=enc)
        return ({'ordered_sha256':hashlib.sha256(enc(entries)).hexdigest(),'sorted_sha256':hashlib.sha256(enc(canon)).hexdigest(),'symbols':len(entries),'references_from_other_sections':users,'raw_symtab':hashlib.sha256(symbols).hexdigest(),'raw_strtab':hashlib.sha256(strings).hexdigest()},canon)
