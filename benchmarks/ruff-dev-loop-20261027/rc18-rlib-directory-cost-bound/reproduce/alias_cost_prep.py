import ast,collections,hashlib,json,mmap,re,subprocess,sys
from pathlib import Path
root=Path(__file__).resolve().parent
e=root/'archive-fs-restore'
dst=root/'alias-cost-v1';dst.mkdir();(dst/'inputs').mkdir();(dst/'outputs').mkdir()
jobs=json.loads((e/'all-jobs.json').read_bytes())['all_rustc_jobs']
pure=[j for j in jobs if j['pure']]
sources={};logical={};extract=lambda x: hashlib.sha256(x).hexdigest()
for j in pure:
    ln=next(l for l in (e/'raw'/('exec.'+str(j['root']))).open()if l.startswith('execve(') and '"--crate-name"' in l and l.rstrip().endswith('= 0'))
    av=ast.literal_eval(re.match(r'^execve\("[^"\\]*", (\[.*\]), ',ln)[1]);out=Path(av[av.index('--out-dir')+1]);assert out not in sources
    sources[out]=j;logical[out]={}
for f in (e/'raw').glob('exec.*'):
    for line in f.open():
        if not line.startswith(('linkat(','link(')) or not line.rstrip().endswith('= 0')or '.rcgu.o"' not in line:continue
        ab=re.findall(r'"([^"\\]+)"',line)
        if len(ab)!=2:continue
        a,b=map(Path,ab);out=b.parent
        if out in sources and b.name.endswith('.rcgu.o') and a.suffix=='.o' and '-working/'in str(a) and 'incremental'in a.parts:
            assert b.name not in logical[out];logical[out][b.name]=a
summary=[];rows=[]
for index,(out,j)in enumerate(sorted(sources.items(),key=lambda pair:pair[1]['name'])):
    target=logical[out];assert len(target)==j['counts']['hardlinked']
    arc=list(out.glob('*.rlib'));assert len(arc)==1
    first=next(iter(target.values()));src_dir=dst/'inputs'/first.parent.parent.name/first.parent.name
    dst_dir=dst/'outputs'/out.parent.name/'out'
    src_dir.mkdir(parents=True);dst_dir.mkdir(parents=True)
    with arc[0].open('rb') as x,mmap.mmap(x.fileno(),0,access=mmap.ACCESS_READ) as body:
        assert body[:8]==b'!<arch>\n';off=8;table=b'';found={}
        while off<len(body):
            hd=body[off:off+60];assert hd[-2:]==b'`\n';size=int(hd[48:58]);start=off+60;tag=hd[:16].strip()
            if tag==b'//':table=body[start:start+size]
            elif tag.startswith(b'/')and tag[1:].isdigit():
                pos=int(tag[1:]);name=table[pos:table.index(b'/\n',pos)].decode()
                if name in target:
                    actual=body[start:start+size];assert actual[:4]==b'\x7fELF'
                    p=src_dir/target[name].name;assert not p.exists();p.write_bytes(actual);found[name]=extract(actual)
            off=start+size+size%2
    assert set(found)==set(target);listing=sorted(found.items())
    for name,_ in listing:rows.append((index,str(src_dir/target[name].name),str(dst_dir/name)))
    summary.append({'crate':j['name'],'archive_sha256':hashlib.file_digest(arc[0].open('rb'),'sha256').hexdigest(),'members':len(target),'member_sha256':extract(json.dumps(listing,separators=(',',':')).encode()),'bytes':sum((src_dir/target[n].name).stat().st_size for n in found)})
assert len(rows)==4212 and len(summary)==30
(dst/'physical-inputs.tsv').write_text(''.join(f'{n}\t{src}\t{alias}\n'for n,src,alias in rows))
subprocess.run(['cc','-std=c11','-O2','-Wall','-Wextra','-Werror',root/'alias_cost.c','-o',dst/'run'],check=True)
(dst/'qualification.json').write_text(json.dumps({'groups':summary,'binary_sha256':extract((dst/'run').read_bytes())},sort_keys=True,indent=2)+'\n')
