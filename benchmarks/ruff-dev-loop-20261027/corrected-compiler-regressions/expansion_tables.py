"""Read the R14 RDR root's stable declaration and expansion tables for this small fixture."""
import gzip
import json
import sys
from pathlib import Path

class Reader:
    def __init__(self, raw):
        assert raw.startswith(b'rust')
        self.raw=raw
        self.root=int.from_bytes(raw[8:16],'little')
        self.i=self.root
        self.previous=None

    def take(self,n):
        val=self.raw[self.i:self.i+n];assert len(val)==n
        self.i+=n
        return val

    def u(self):
        value=0
        for i in range(10):
            b=self.take(1)[0]
            value|=(b&127)<<(7*i)
            if b<128:return value
        raise ValueError('invalid LEB128')

    def string(self):
        val=self.take(self.u());assert self.take(1)==b'\xc1'
        return val

    def symbol(self):
        k=self.u()
        if k==0:return self.string()
        assert k in (1,2)
        return self.u()

    def lazy(self):
        distance=self.u()
        self.previous=self.root-distance if self.previous is None else self.previous+distance
        assert 0<self.previous<=self.root
        return self.previous

    def array(self):
        if self.u():self.lazy()

    def table(self):
        return self.u(),self.u(),self.lazy()

    def rows(self, tab):
        raw_width,n,at=tab
        width=raw_width&~128
        assert 0<=width<=17 and n<100000
        occupied=[True]*n
        if raw_width&128:
            occupied=[]
            for i in range(0,n,64):
                bitmap=int.from_bytes(self.raw[at:at+8],'little')
                previous=int.from_bytes(self.raw[at+8:at+12],'little')
                assert previous==sum(occupied)
                at+=12
                occupied.extend(bool(bitmap&(1<<j)) for j in range(min(64,n-i)))
        rows=[]
        for active in occupied:
            if active:
                rows.append(int.from_bytes(self.raw[at:at+width],'little'));at+=width
            else:rows.append(0)
        return rows

    def interface(self):
        # The initial tag is the builtin target. CrateHeader stores a triple, 2 hashes, symbol name
        # and two booleans. The following fields are fixed by the anchored compiler source.
        assert self.u()==0;self.string();self.take(32);self.symbol();self.take(2)
        self.string();self.take(8)
        if self.u(): self.u()
        self.u();self.u();self.take(4)
        for _ in range(13):self.array()
        assert self.u()==1
        for _ in range(3):self.array()
        assert self.u()==0
        for _ in range(5):self.array()
        tables=[self.table()for _ in range(88)]
        self.table();self.table()
        hashes=self.rows(self.table())
        def_hashes=self.rows(tables[4]);definitions=self.rows(tables[66])
        by_def={}
        for i,ident in enumerate(def_hashes):
            pos=definitions[i] if i<len(definitions) else 0
            if pos:
                self.i=pos;owner,index=self.u(),self.u()
                if owner==0:by_def[f'{ident:016x}']=index
        return by_def,[self.raw[at:at+16].hex() if at else None for at in hashes]

def load_metadata(case,phase,unit):
    all_messages=[json.loads(row) for row in gzip.decompress((case/phase/'cargo.stdout.gz').read_bytes()).splitlines()]
    p=next(Path(f) for m in all_messages if m.get('reason')=='compiler-artifact'and m['target']['name']==unit for f in m['filenames'] if f.endswith('.rmeta'))
    return p.read_bytes()

if __name__=='__main__':
    root=Path(sys.argv[1])
    evidence={}
    for name,unit in [('foreign-expn-disappears','leaf'),('local-expn-disappears','bundle'),
                      ('foreign-expn-shrink','leaf'),('local-expn-shrink','bundle')]:
        a,b=[Reader(load_metadata(root/name,n,unit)).interface() for n in ['caller-restore-clean','caller-clean']]
        aa,old_hashes=a;bb,new_hashes=b
        entries=[]
        for d in aa.keys()&bb.keys():
            x,y=aa[d],bb[d]
            if x==0 or x==y:continue
            old=old_hashes[x];new=new_hashes[y] if y and y<len(new_hashes) else None
            entries.append(dict(declaration=d,old_index=x,new_index=y,old_hash=old,new_hash=new,old_hash_absent=old not in new_hashes))
        if 'disappears' in name: assert any(v['old_hash_absent'] and v['new_index']==0 for v in entries),(name,entries)
        else: assert any(v['old_hash']==v['new_hash'] and v['new_hash'] for v in entries),(name,entries)
        evidence[name]=dict(crate=unit,transitions=entries)
    (root/'physical-expansions.json').write_text(json.dumps(evidence,indent=2,sort_keys=True)+'\n')
    print('verified',len(evidence),'local/foreign physical expansion transitions')
