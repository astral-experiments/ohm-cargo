"""Read only GNU ar headers and their string table in preserved actual libraries."""
import hashlib,json,os,re
from pathlib import Path
import sys

def stat_headers(p):
    def sha(b):return hashlib.sha256(b).hexdigest()
    raw=p.stat().st_size;reads=0
    with p.open('rb',buffering=0) as f:
        def rd(n):
            nonlocal reads
            d=f.read(n);reads+=len(d);return d
        assert rd(8)==b'!<arch>\n'
        sections=[];names=b''
        while f.tell()<raw:
            h=rd(60);assert len(h)==60 and h[-2:]==b'`\n';sz=int(h[48:58]);off=f.tell()
            field=h[:16].rstrip(b' ')
            if field==b'//':names=rd(sz)
            elif field not in (b'/',b'/SYM64/'):
                if field.startswith(b'/'):
                    start=int(field[1:]);end=names.index(b'/\n',start);name=names[start:end].decode()
                else:name=field.removesuffix(b'/').decode()
                sections.append((name,sz))
            f.seek(off+sz+(sz%2),os.SEEK_SET)
        assert f.tell()==raw
    assert [n for n,_ in sections[:2]]==['lib.rmeta','lib.rmeta-link']
    key=lambda n:n.removesuffix('.rcgu.o').rsplit('.',1)[0]
    assert all(n.endswith('.rcgu.o') and len(n.removesuffix('.rcgu.o').rsplit('.',1)[1])==7 for n,_ in sections[2:])
    bodies=[(key(n),s) for n,s in sections[2:]]
    return ({'raw_bytes':raw,'archive_filename_sha256':p.name,'read_bytes':reads,'gnu_name_table_bytes':len(names),
             'raw_native_member_count':len(bodies),'metadata_bytes':[s for _,s in sections[:2]],
             'native_length_vector':sha(json.dumps([s for _,s in bodies]).encode()),
             'stable_name_and_length_vector':sha(json.dumps(bodies).encode())},bodies)

def main(base):
    observations={}
    for case in ['pydantic-build','pydantic-test','ty-comment-test']:
        products=[]
        for state in ['original','changed']:
            donor=json.loads((base/case/state/'probe.json').read_bytes())['archives']
            assert len(donor)==1
            key,entry=next(iter(donor.items()))
            assert Path(key).name.startswith('libty_python_semantic') and Path(key).suffix=='.rlib'
            p=Path(entry['copy']);p=p if p.is_file() else base/case/'archives'/entry['file_sha256']
            assert p.name==entry['file_sha256']
            products.append(stat_headers(p))
        (old,a),(new,b)=products
        assert len(a)==len(b)
        changes=[{'ordinal':i,'before_bytes':xs,'after_bytes':ys} for i,((xn,xs),(yn,ys)) in enumerate(zip(a,b)) if xs!=ys]
        records=base/case/'changed'/'execs';lines=records.read_bytes().splitlines()
        links=[s for s in lines if re.search(rb'execve\("[^"]*/ld\.bfd",\s*\[',s) and s.rstrip().endswith(b'= 0')]
        observations[case]={'patch_sha256':hashlib.sha256((base/case/'edit.patch').read_bytes()).hexdigest(),'original':old,'changed':new,
                'stable_native_names':sum(x[0]==y[0] for x,y in zip(a,b)),'native_size_changes':changes,
                'successful_physical_wild':len(links),'containing_producer_rlib_argv':sum(b'/libty_python_semantic-' in s and b'.rlib"' in s for s in links),
                'historical_trace_sha256':hashlib.sha256(records.read_bytes()).hexdigest()}
    return observations

if __name__=='__main__':print(json.dumps(main(Path(sys.argv[1])),sort_keys=True,indent=2))
