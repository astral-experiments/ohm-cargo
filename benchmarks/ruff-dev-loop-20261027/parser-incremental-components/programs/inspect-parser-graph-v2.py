"""Decode the actual provider's incoming query keys from the unmodified release incremental dependency graph."""
import collections, gzip, hashlib, json, struct
from pathlib import Path

study=Path("/mnt/devbox-scratch/dev-user/ohm-whole-skips-20261027/mixed-registry-only-pilot/parser-incremental-components")
target=study.parent/"parser-component-graph-edges-v2"; target.mkdir()
manifest=json.loads(Path(__file__).with_name("parser-graph-kinds.json").read_bytes())

def leb(d,p):
    value=0
    for i in range(10):
        b=d[p];p+=1;value|=(b&127)<<(7*i)
        if b<128:return value,p
    raise ValueError("unterminated LEB")

def decode(f,names):
    d=f.read_bytes();assert d.startswith(b"RSIC\x02\0") and d.endswith(b"rust-end-file")
    nmax,n,ne=struct.unpack_from("<QQQ",d,len(d)-13-24);assert n<=nmax
    p=7+d[6]+8; graph_start=p;bits=(len(names)-1).bit_length()
    counts=collections.Counter();keys={};id_edges={};num=0
    for _ in range(n):
        flags,idx=struct.unpack_from("<HI",d,p);kind=flags&((1<<bits)-1);width=1+((flags>>bits)&3);length=(flags>>(bits+2))-1
        assert 0<kind<len(names) and idx not in keys and idx<nmax,(p,kind,idx,n,nmax,len(names))
        key=d[p+6:p+22];value=d[p+22:p+38];p+=38
        if length<0:length,p=leb(d,p)
        keys[idx]=(kind,key.hex(),value.hex());counts[kind]+=1;num+=length
        if names[kind]=="crate_hash":
            id_edges[idx]=[int.from_bytes(d[q:q+width],"little") for q in range(p,p+width*length,width)]
        p+=width*length
    assert num==ne
    for k in range(len(names)):
        count,p=leb(d,p)
        assert counts[k]==count,(k,names[k],count,counts[k])
    assert any(id_edges)
    allroots={}
    for i,children in id_edges.items():
        root=keys[i];ch={f"{names[keys[j][0]]}|{keys[j][1]}":keys[j][2] for j in children};assert len(ch)==len(set(children))
        allroots[root[1]]={"value_fingerprint":root[2],"direct_query_values":ch,"edges_sha256":hashlib.sha256(json.dumps(ch,sort_keys=True).encode()).hexdigest()}
    return {"file_sha256":hashlib.sha256(d).hexdigest(),"node_count":n,"edge_count":ne,"graph_start":graph_start,"compiler_abi":d[7:7+d[6]].decode(),"roots":allroots}
def dump(path,obj):path.write_text(json.dumps(obj,indent=2,sort_keys=True)+"\n")
allresults={}
for arm in ["B","A"]:
    states={}
    for state in ["all","empty"]:
        base=study/arm/state/"physical/target/debug/incremental";files=list(base.glob("*/ruff_python_parser-*/s-*-*-*/dep-graph.bin"));assert len(files)==1,files
        states[state]=decode(files[0],manifest[arm]["kinds"])
        b=(json.dumps(states[state],sort_keys=True,indent=2)+"\n").encode();(target/f"{arm}-{state}-roots.json.gz").write_bytes(gzip.compress(b,compresslevel=6,mtime=0))
    a,b=[states[s]["roots"] for s in ["all","empty"]];assert set(a)==set(b)
    # The LOCAL provider reads the HIR of the parser. The forwarded crates have a tiny dependency set.
    rootk,=[k for k,r in a.items() if any(q.startswith("hir_crate_items|") for q in r["direct_query_values"])]
    aa=a[rootk]["direct_query_values"];bb=b[rootk]["direct_query_values"]
    changed={q:[aa[q],bb[q]] for q in aa.keys()&bb.keys() if aa[q]!=bb[q]}
    allresults[arm]={"root_key":rootk,"root_value_fingerprint":[a[rootk]["value_fingerprint"],b[rootk]["value_fingerprint"]],
      "direct_edge_counts":[len(aa),len(bb)],"same_keys_same_values":sum(q in bb and aa[q]==bb[q] for q in aa),
      "warm_only_keys":{k:aa[k] for k in aa.keys()-bb.keys()},"cold_only_keys":{k:bb[k] for k in bb.keys()-aa.keys()},
      "changed_direct_query_values":changed,"kind_histograms":[dict(collections.Counter(q.split("|")[0] for q in z)) for z in (aa,bb)]}
    dump(target/"comparison.json",allresults)
    print(arm,rootk,len(aa),len(bb),"different",len(changed),"warm-only",len(aa.keys()-bb.keys()),"cold-only",len(bb.keys()-aa.keys()),dict(collections.Counter(k.split("|")[0] for k in changed)),flush=True)
