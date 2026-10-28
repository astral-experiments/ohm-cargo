"""Attribute a returned Callgrind event total to its physical functions and direct calls."""
from collections import Counter,defaultdict
import argparse,re,json
from pathlib import Path
def parse(path):
    func_names={};self_ir=Counter();edges=Counter();ncalls=Counter()
    ident=callee=None;pending=0;positions=1;summary=None
    for line in path.open(errors='replace'):
        ln=line.strip()
        if ln.startswith('positions:'):positions=len(ln.split()[1:])
        elif ln.startswith('summary:'):summary=int(ln.split()[1])
        elif m:=re.match(r'^(c?fn)=\((\d+)\)(?: (.*))?$',ln):
            idx=int(m[2])
            if m[3]:func_names[idx]=m[3]
            if m[1]=='fn':ident=idx;pending=0
            else:callee=idx
        elif ln.startswith('calls='):pending=int(ln.split()[0].split('=')[1])
        elif ln and ln[0] in '*+-0123456789':
            cols=ln.split()
            if len(cols)<=positions or ident is None:continue
            cost=int(cols[positions])
            if pending:
                edges[(ident,callee)]+=cost;ncalls[(ident,callee)]+=pending;pending=0
            else:self_ir[ident]+=cost
    return func_names,self_ir,edges,ncalls,summary
def main():
    p=argparse.ArgumentParser();p.add_argument('path',type=Path);p.add_argument('--match');p.add_argument('--top',type=int,default=30);opts=p.parse_args()
    names,own,edges,ncalls,total=parse(opts.path);assert abs(sum(own.values())-total)<2000000,(sum(own.values()),total)
    if not opts.match:
        print('total',total,'self',sum(own.values()),'functions',len(own),'edges',len(edges))
        for idx,n in own.most_common(opts.top):
            print(n, f'{n*100/total:.2f}%',names.get(idx,idx))
    else:
        matched={i for i,n in names.items() if re.search(opts.match,n)}
        print('matched',len(matched),'direct Ir',sum(own[i] for i in matched),'of',total)
        for what,test,index in [('from',lambda parent,child:child in matched and parent not in matched,0),('into',lambda parent,child:parent in matched and child not in matched,1)]:
            c=Counter();calls=Counter()
            for edge,ir in edges.items():
                if test(*edge):c[edge[index]]+=ir;calls[edge[index]]+=ncalls[edge]
            for i,n in c.most_common(opts.top):print(what,n,calls[i],names.get(i,i))
if __name__=='__main__':main()
