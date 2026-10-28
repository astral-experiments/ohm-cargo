"""Decode weighted basic blocks and direct calls from one terminal DynamoRIO process."""
import bisect,collections,hashlib,json,re,struct,subprocess,sys
from pathlib import Path
p=Path(sys.argv[1]);out=p.parent;root=Path('/mnt/devbox-scratch/dev-user/ohm-early-completion-20261027/spaced-dirty-attribution-20261028/software-counters/callgrind/usr/lib/debug')
raw=p.read_bytes();mark=re.search(rb'^D\t(\d+)\t(\d+)\n',raw,re.M);assert mark
blocks,size=map(int,mark.groups());assert size==32
head=raw[:mark.start()].decode().splitlines();tail=raw[mark.end()+blocks*size:].decode().splitlines();body=raw[mark.end():mark.end()+blocks*size]
pid,=[v.split('\t')[1] for v in head if v.startswith('B\t')];assert tail==['E\t'+pid]
threads=sorted(v[2:] for v in head if v.startswith('T\t'));exits=sorted(v[2:] for v in head if v.startswith('F\t'));assert threads==exits and len(threads)==len(set(threads))
mods=[]
for x in head:
    if x.startswith('M\t'):
        _,a,b,n=x.split('\t',3);mods.append((int(a,16),int(b,16),n))
mods=sorted(set(mods));mb=[x[0] for x in mods]
def cmd(args):return subprocess.run(args,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,text=True).stdout
def symbols(n):
    p=Path(n)
    if not p.is_file():return [],[],None
    build_id=re.search(r'Build ID: ([a-f0-9]+)',cmd(['readelf','-nW',p]))
    debug=root/'.build-id'/build_id[1][:2]/(build_id[1][2:]+'.debug') if build_id else None
    if debug and debug.is_file():p=debug
    raw=cmd(['nm','-nS','--defined-only','-C',p])
    if not raw:raw=cmd(['nm','-nSD','--defined-only','-C',p])
    items={}
    for s in raw.splitlines():
        m=re.match(r'^([0-9a-fA-F]+) (?:(\w+) )?([tTwWiI]) (.+)$',s)
        if not m:continue
        try:i,sz=int(m[1],16),int(m[2],16) if m[2] else 0
        except ValueError:continue
        if sz>items.get(i,(-1,''))[0]:items[i]=(sz,m[4])
    addrs=sorted(items);return addrs,[items[a] for a in addrs],p
tables={}
def name(pc):
    i=bisect.bisect_right(mb,pc)-1
    if i<0 or pc>=mods[i][1]:return ('unmapped',0)
    base,_,module=mods[i];off=pc-base
    if module not in tables:tables[module]=symbols(module)
    addrs,items,_=tables[module];i=bisect.bisect_right(addrs,off)-1;mod=Path(module).name
    if i<0:return (mod+':unresolved',off)
    s,n=items[i]
    if s and off>=addrs[i]+s:return (mod+':unresolved-after-'+n,off)
    return mod+':'+n,off
own=collections.Counter();modules=collections.Counter();dce=collections.Counter();unknown=0
for cnt,pc,call,n,_ in struct.iter_unpack('<QQQII',body):
    if not cnt:continue
    nm,off=name(pc);ir=cnt*n;own[nm]+=ir;modules[nm.split(':',1)[0]]+=ir
    if 'unresolved' in nm or nm=='unmapped':unknown+=ir
    if call:
        target,_=name(call);dce[(nm,target)]+=cnt
result={'total':sum(own.values()),'modules':modules,'unresolved':unknown,'threads':len(threads),'translations':blocks,'profile_sha256':hashlib.sha256(raw).hexdigest(),'reported_modules':len(mods)}
(out/'top.json').write_text(json.dumps(result,sort_keys=True,indent=2)+'\n')
with (out/'functions.tsv').open('w') as f:
    for k,v in own.most_common():f.write(f'{v}\t{k}\n')
with (out/'calls.tsv').open('w') as f:
    for (caller,callee),n in dce.most_common():f.write(f'{n}\t{caller}\t{callee}\n')
print(json.dumps(result,sort_keys=True))
