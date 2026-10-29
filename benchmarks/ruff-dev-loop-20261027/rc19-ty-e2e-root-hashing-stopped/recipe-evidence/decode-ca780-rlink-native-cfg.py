"""Decode the pinned rlink fields through native library cfg spans for this Linux workload."""
import hashlib
import json
from pathlib import Path
import sys

def digest(data):
    return hashlib.sha256(data).hexdigest()

class Decoder:
    def __init__(self,data):
        self.data = data
        self.pos = 0
        self.spans = []

    def take(self,n):
        assert 0 <= n <= len(self.data)-self.pos,(self.pos,n)
        out = self.data[self.pos:self.pos+n]
        self.pos += n
        return out

    def tag(self,limit):
        v = self.take(1)[0]
        assert v < limit,(self.pos-1,v,limit)
        return v

    def num(self):
        start = self.pos
        value = 0
        for shift in range(0,64,7):
            byte = self.take(1)[0]
            value |= (byte & 127) << shift
            if byte < 128:
                assert self.pos-start == max(1,(value.bit_length()+6)//7)
                return value
        raise ValueError("unterminated LEB128 integer")

    def string(self):
        raw = self.take(self.num())
        assert self.take(1)==b"\xc1"
        return raw.decode("utf-8")

    def option(self,fn):
        return fn() if self.tag(2) else None

    def seq(self,fn):
        count = self.num()
        assert count <= 8192
        return [fn() for _ in range(count)]

    def module(self):
        name = self.string()
        kind = self.tag(2)
        outputs = [self.option(self.string) for _ in range(6)]
        cached = self.seq(self.string)
        assert outputs[0] and all(x is None for x in outputs[1:]) and len(cached) <= 1
        return name,kind

    def span(self,context):
        start = self.pos
        lo = self.num()
        hi = self.num()
        assert lo <= hi <= 0xffffffff
        self.spans.append(dict(context=context,offset=start,end=self.pos,lo=lo,hi=hi))
        return lo,hi

    def cfg(self,context,depth=0):
        assert depth < 16
        tag = self.tag(6)
        ctx = context+[tag]
        if tag in (0,1):
            value = self.seq(lambda:self.cfg(ctx,depth+1))
        elif tag==2:
            value = self.cfg(ctx,depth+1)
        elif tag==3:
            value = self.tag(2)
        elif tag==4:
            value = [self.string(),self.option(self.string)]
        else:
            value = self.option(lambda:[int.from_bytes(self.take(2),"little") for _ in range(3)])
        self.span(ctx+[value])
        return [tag,value]

    def native(self,krate,index):
        kind = self.tag(7)
        nopts = 3 if kind==0 else 1 if kind in (1,2,3) else 0
        flags = [self.option(lambda:self.tag(2)) for _ in range(nopts)]
        name = self.string()
        cfg = self.option(lambda:self.cfg([krate,index,name]))
        verbatim = self.tag(2)
        count = self.num()
        assert count==0,"unexpected DLL imports on the measured Linux target"
        return [kind,flags,name,cfg,verbatim]

    def natives(self,krate):
        count = self.num()
        assert count <= 50
        return [self.native(krate,i) for i in range(count)]

    def run(self):
        assert self.take(12)==b"rustlink\x00\x00\x00\x01" and self.data.endswith(b"rust-end-file")
        version = self.string()
        assert "ca780121" in version
        modules = self.seq(self.module)
        allocator = self.option(self.module)
        assert len(modules)==138 and len(set(n for n,k in modules))==138 and all(k==0 for _,k in modules)
        assert allocator and allocator[1]==1
        start = self.pos
        cpu = self.string()
        features = self.seq(self.string)
        types = self.seq(lambda:self.tag(7))
        exports = self.seq(lambda:(self.tag(7),self.seq(lambda:(self.string(),self.tag(3),self.option(self.string)))))
        linked = self.seq(lambda:(self.tag(7),self.seq(lambda:(self.string(),self.tag(3)))))
        root = self.string()
        builtins = self.option(self.num)
        profiler = self.option(self.num)
        no_builtin = self.seq(self.num)
        prefix_end = self.pos
        count = self.num()
        assert 1 <= count <= 1024
        libs = {}
        for _ in range(count):
            crate = self.num()
            assert crate not in libs
            libs[crate] = self.natives(crate)
        names = dict(self.seq(lambda:(self.num(),self.string())))
        assert set(names) == set(libs)
        root_libs = self.natives(0)
        assert root == "e2e"
        return dict(crate_info_start=start,libraries_start=prefix_end,after_libraries=self.pos,
                    root=root,cpu=cpu,features=features,types=types,indexed_crates=count,
                    exported=len(exports),linked=len(linked),builtins=builtins,profiler=profiler,
                    no_builtins=no_builtin,libraries={str(k):[names[k],v] for k,v in libs.items() if v},
                    root_libraries=root_libs,spans=self.spans)

def main(folder):
    out = {}
    for file in sorted(folder.glob("*.rlink")):
        raw = file.read_bytes()
        d = Decoder(raw).run()
        d["input_sha256"] = digest(raw)
        out[file.stem] = d
    assert len(out)==8
    print(json.dumps(out,indent=2,sort_keys=True))

if __name__=="__main__":
    main(Path(sys.argv[1]))
