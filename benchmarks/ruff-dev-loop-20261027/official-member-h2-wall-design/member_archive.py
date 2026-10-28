"""Preserve a complete archive witness and fold only its exact declared, per-CGU temporary names."""
from pathlib import Path
import hashlib,json,mmap,re,struct
from member_archive_base import inspect
sha=lambda b:hashlib.sha256(b).hexdigest()
def encode(obj):return json.dumps(obj,sort_keys=True,separators=(',',':')).encode()
def name_key(s):
    prefix,nonce,typ,ext=s.rsplit('.',3)
    assert re.fullmatch(r'[A-Za-z0-9_.-]+',prefix) and re.fullmatch(r'[0-9a-z]{1,15}',nonce) and (typ,ext)==('rcgu','o')
    return prefix+'.@nonce@.rcgu.o'

def link_wrapper(raw):
    # Retain all ELF fields except physical file offsets and the size of the decoded name roster.
    assert raw[:7]==b'\x7fELF\x02\x01\x01' and struct.unpack_from('<HH',raw,16)==(1,62)
    table=struct.unpack_from('<Q',raw,40)[0];eh,phstride,phcount,shstride,num,idx=struct.unpack_from('<6H',raw,52)
    assert eh==64 and phcount==0 and shstride==64 and table+64*num==len(raw)
    hdr=bytearray(raw[:64]);hdr[40:48]=bytes(8)
    heads=[struct.unpack_from('<IIQQQQIIQQ',raw,table+j*64) for j in range(num)]
    ss=heads[idx];names=raw[ss[4]:ss[4]+ss[5]];regions=[(0,64),(table,len(raw))];stable=[]
    for nameoff,typ,flags,addr,off,size,link,info,align,entsize in heads:
        end=names.index(0,nameoff);name=names[nameoff:end].decode('ascii')
        if size:regions.append((off,off+size))
        assert typ!=8
        if name=='.rmeta-link':assert flags==0x80000000
        stable.append([nameoff,name,typ,flags,addr,link,info,align,entsize,None if name=='.rmeta-link' else [size,sha(raw[off:off+size])]])
    prev=0
    for lo,hi in sorted(regions):
        assert lo>=prev and hi<=len(raw) and not any(raw[prev:lo]),('nonzero or overlapping ELF padding',lo,prev)
        prev=hi
    assert prev==len(raw)
    return [bytes(hdr).hex(),stable]

def witness(path):
    rec=inspect(path)
    names=[x[0] for x in rec['objects']];lookup={n:name_key(n) for n in names}
    assert len(set(lookup.values()))==len(names)
    headers=[];longs=None;specials={}
    with path.open('rb') as f,mmap.mmap(f.fileno(),0,access=mmap.ACCESS_READ) as data:
        pos=8
        while pos<len(data):
            header=data[pos:pos+60];label=header[:16].rstrip();size=int(header[48:58]);begin=pos+60;end=begin+size
            assert header[58:]==b'`\n' and end<=len(data)
            if end%2:assert data[end:end+1]==b'\n'
            if label==b'/': role='symbol-index'
            elif label==b'//':
                role='name-table';entries=data[begin:end]
                # Rust writes long filenames as GNU '/newline' entries, with at most one newline of alignment.
                parts=entries.split(b'/\n');assert parts[-1] in (b'',b'\n')
                raw_names=[x.decode('ascii') for x in parts[:-1]];assert set(raw_names)<=set(lookup)
                longs=entries;specials['long_order']=[lookup[x] for x in raw_names]
            else:
                if label.startswith(b'/'):
                    assert longs is not None and label[1:].isdigit()
                    off=int(label[1:]);assert off==0 or longs[off-2:off]==b'/\n'
                    name=longs[off:longs.index(b'/\n',off)].decode('ascii')
                else:name=label.removesuffix(b'/').decode('ascii')
                role=lookup.get(name,name);assert role in ('lib.rmeta','lib.rmeta-link') or name in lookup
                if name=='lib.rmeta':specials['full_metadata_wrapper']=sha(memoryview(data)[begin:end])
                if name=='lib.rmeta-link':specials['full_link_wrapper_structure']=link_wrapper(data[begin:end])
            headers.append([role,header[16:48].decode('ascii')]);pos=end+end%2
        assert pos==len(data) and set(specials)=={'long_order','full_metadata_wrapper','full_link_wrapper_structure'}
    projection=dict(headers=headers,specials=specials,objects=[[lookup[n],z,h] for n,z,h in rec['objects']],
                    symbol_count=rec['symbol_index_entries'],symbol_name_member_ordinals=rec['symbol_name_member_ordinal_sha256'],
                    referenced=rec['referenced_object_member_ordinals'],link_roster=rec['rmeta_link'])
    return dict(raw=rec['sha256'],typed=sha(encode(projection)),projection=projection,
                original_names=names,wrappers=rec['wrappers'])
