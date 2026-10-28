"""Compare Cargo's seven complete product fields, rewriting only the actual workspace backend token in typed paths."""
from collections import Counter
from pathlib import Path, PurePosixPath
import hashlib,json,re,sys
P=PurePosixPath('/mnt/devbox-scratch/dev-user/ohm-empty-test-h4-20261027/native-target')
WORKSPACE='38b7ca2992c44384'
MARK='@observed-compiler@'
ENC=lambda x:json.dumps(x,sort_keys=True,separators=(',',':'))
sha=lambda x:hashlib.sha256(x).hexdigest()
def token(paths):
    stamps={v for n in paths for p in [PurePosixPath(n).relative_to(P).parts] if p[:3]==('debug','build','workspaces') for v in [p[4]] if p[3]==WORKSPACE}
    t,=stamps;assert re.fullmatch(r'v2-[0-9a-f]{16}',t);return t
def key(name,stamp):
    x=PurePosixPath(name);assert str(x)==name and x.is_relative_to(P) and '..' not in x.parts and MARK not in name
    p=x.relative_to(P).parts
    if p[:3]==('debug','build','workspaces'):
        assert len(p)>=8 and p[3:5]==(WORKSPACE,stamp)
        return str(P.joinpath(*p[:4],MARK,*p[5:]))
    return str(x)
def canonical(stdout,stamp):
    rows=[json.loads(line) for line in stdout.read_bytes().splitlines()]
    arts=[r for r in rows if r.get('reason')=='compiler-artifact'];assert len(arts)==619
    raw=[];normal=[];count=Counter()
    for r in arts:
        unit={k:r[k] for k in ('package_id','manifest_path','target','profile','features','filenames','executable')}
        raw.append(json.dumps(unit,sort_keys=True))
        for k in ('filenames','executable'):
            if k=='filenames':
                ns=[key(n,stamp) for n in unit[k]];count[k]+=sum(n!=m for n,m in zip(unit[k],ns));unit[k]=ns
            elif unit[k] is not None:
                original=unit[k];unit[k]=key(original,stamp);count[k]+=unit[k]!=original
        normal.append(json.dumps(unit,sort_keys=True))
    digest=lambda fields:sha(ENC(sorted(fields)).encode())
    return {'units':len(arts),'raw':digest(raw),'typed':digest(normal),'number_of_changed_typed_fields':dict(count)}
def compare(root):
    MOD=Path(__file__).resolve().parent;sys.path.insert(0,str(root/'protocol'));from elf_gate import permitted_linker_width
    out={'arms':{},'products':{},'cross':{},'proofs':{}};full={};dirs=root/'results';proofs={}
    for a in 'OABC':
        d=dirs/('unscored-'+a);cold=d/'cold/elf.json'
        if not cold.is_file() or not (d/'cold/record.json').exists():continue
        native=json.loads(cold.read_bytes());assert len(native)==110
        t=token(native);phases={};full[a]={}
        for ph in ('cold','first','settled','settled2'):
            fold=d/ph
            if not (fold/'record.json').exists():continue
            rec=json.loads((fold/'record.json').read_bytes());nu=canonical(fold/'stdout',t);assert nu['raw']==rec['roster'] and rec['elapsed_ns'] is None
            phases[ph]=nu
            if (fold/'elf.json').exists():
                m=json.loads((fold/'elf.json').read_bytes());assert token(m)==t
                vals={key(n,t):v for n,v in m.items()};assert len(vals)==110;full[a][ph]=vals
                if ph=='cold' or ph=='first':
                    pr=json.loads((fold/'observer/proof.json').read_bytes());proofs[a,ph]=pr
        out['arms'][a]={'observed_workspace_namespace':t,'rosters':phases,'executable_paths':len(native),'changed_executable_paths':sum(key(n,t)!=n for n in native)}
    for a in 'ABC':
        if a not in full or 'O' not in full:continue
        out['cross'][a]={}
        for phase in full[a]:
            left=full['O'][phase];right=full[a][phase];assert left.keys()==right.keys()
            unequal={n for n,v in right.items() if v!=left[n]};known={n for n in unequal if permitted_linker_width(left[n],right[n])}
            unavailable=[]
            for n in sorted(unequal-known):
                l=left[n];r=right[n];unavailable.append({'path':str(PurePosixPath(n).relative_to(P)),'base':l,'subject':r})
            out['cross'][a][phase]={'raw_equal':110-len(unequal),'proved_wild_width_only':len(known),'all_other_mismatches':unavailable}
    if ('C','cold') in proofs and ('B','first') in proofs:
        c=proofs['C','cold']['optional_inputs'];b=proofs['B','first']['regular_inputs'];out['proofs']={'C_first_observed':len(c),'B_conventional':len(b),'byte_and_path_exact':c==b,'C_digest':sha(ENC(c).encode()),'B_digest':sha(ENC(b).encode())}
    return out
if __name__=='__main__':print(json.dumps(compare(Path(sys.argv[1])),sort_keys=True,indent=2))
