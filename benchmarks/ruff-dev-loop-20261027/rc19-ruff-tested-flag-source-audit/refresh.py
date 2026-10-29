"""Refresh the published head/file inventory without fetching into either checkout."""
import argparse
import base64
import concurrent.futures
import gzip
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess

RUF = '93526150df078af7dd8fc4226cdcc469539d2001'
CHANGE = 'b647f3fba81128ae586058b6c0937a3e03c1a997'
REL = '7caf39914da1e28a67744ecbc963a5f26361474d'
RC = '235f9228651b74c591e6f62cae4c9b761448dd2d'
MANIFEST = 'crates/ruff_benchmark/Cargo.toml'
PATHS = ['src/compiler/fingerprint/mod.rs', 'src/cargo/core/compiler/fingerprint/mod.rs',
         'src/workspace/manifest.rs', 'src/cargo/core/manifest.rs']
DETAIL = ['src/compiler/build_runner/compilation_files.rs', 'src/compiler/mod.rs',
          'src/ops/cargo_compile/unit_generator.rs', 'src/workspace/parser/targets.rs']
ARMS = {'ohm-cargo': [161, 263, 268, 275, 276], 'ohm-rust': [25, 58]}
ENV = dict(os.environ, GIT_NO_LAZY_FETCH='1', GIT_OPTIONAL_LOCKS='0')


def git_blob(data):
    return hashlib.sha1(b'blob '+str(len(data)).encode()+b'\0'+data).hexdigest()


def run(directory, args, *, data=None, check=True):
    return subprocess.run(args, cwd=directory, input=data, capture_output=True,
                          env=ENV, check=check)


def main():
    cli=argparse.ArgumentParser(description=__doc__)
    cli.add_argument('cargo_checkout',type=Path)
    cli.add_argument('ruff_checkout',type=Path)
    cli.add_argument('output',type=Path,help='New sibling directory for a newly dated inventory')
    args=cli.parse_args()
    cargo=args.cargo_checkout.resolve(); ruff=args.ruff_checkout.resolve()
    dest=args.output; dest.mkdir(exist_ok=False)
    gh=shutil.which('gh-auto')
    assert gh and run(cargo,[gh,'api','user','--jq','.login']).stdout.strip()==b'charliermarsh'

    def api(cmd,data=None):
        return json.loads(run(cargo,[gh,'api',*cmd],data=data).stdout)

    def pages(request):
        return [r for page in api(['--paginate','--slurp','repos/astral-sh/ohm-cargo/'+request]) for r in page]

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as jobs:
        b,p=jobs.map(pages,['branches?per_page=100','pulls?state=all&per_page=100'])
    branches={r['name']:r['commit']['sha'] for r in b}
    prs={str(r['number']):{'head':r['head']['sha'],'state':r['state']} for r in p}
    tips=sorted(set(branches.values())|{r['head'] for r in prs.values()})

    def locate(group):
        fields=[f'x{i}p{j}:object(expression:"{h}:{f}"){{oid}}' for i,h in enumerate(group) for j,f in enumerate(PATHS)]
        query='query { repository(owner:"astral-sh",name:"ohm-cargo"){ '+' '.join(fields)+' } }'
        res=api(['graphql','--input','-'],json.dumps({'query':query}).encode())['data']['repository']
        return {h:{f:res[f'x{i}p{j}']['oid'] for j,f in enumerate(PATHS) if res[f'x{i}p{j}']} for i,h in enumerate(group)}

    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as jobs:
        source={h:files for rows in jobs.map(locate,[tips[i:i+25] for i in range(0,len(tips),25)]) for h,files in rows.items()}

    def cargo_blob(oid):
        r=run(cargo,['git','cat-file','blob',oid],check=False)
        raw=r.stdout if r.returncode==0 else base64.b64decode(api(['repos/astral-sh/ohm-cargo/git/blobs/'+oid])['content'])
        assert git_blob(raw)==oid
        return oid,raw

    def from_tree(repo,head,part):
        oid=run(repo,['git','rev-parse',head+':'+part]).stdout.decode().strip()
        raw=run(repo,['git','cat-file','blob',oid]).stdout
        assert git_blob(raw)==oid
        return oid,raw

    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as jobs:
        raw=dict(jobs.map(cargo_blob,sorted({v for d in source.values() for v in d.values()})))
    extra={}
    for head in (REL,RC):
        extra[head]={}
        for f in [PATHS[0],PATHS[2],*DETAIL]:
            oid,v=from_tree(cargo,head,f); raw[oid]=v; extra[head][f]=oid

    prior=run(ruff,['git','rev-parse',CHANGE+'^']).stdout.decode().strip()
    historical=run(ruff,['git','diff-tree','--no-commit-id','--name-only','-r',CHANGE]).stdout.decode().splitlines()
    assert historical==[MANIFEST]
    ruff_files={}
    for ref,files in [(prior,[MANIFEST]),(CHANGE,[MANIFEST]),(RUF,[MANIFEST,'Cargo.toml','crates/ruff_benchmark/src/lib.rs'])]:
        ruff_files[ref]={}
        for f in files:
            oid,v=from_tree(ruff,ref,f); raw[oid]=v; ruff_files[ref][f]=oid
    member_refs=run(ruff,['git','grep','-n','-w','ruff_benchmark',RUF,'--',':(glob)**/Cargo.toml']).stdout.decode().splitlines()
    resources=run(ruff,['git','ls-tree','-r','--name-only',RUF,'crates/ruff_benchmark/src','crates/ruff_benchmark/build.rs']).stdout.decode().splitlines()

    comparisons={}
    for repo,numbers in ARMS.items():
        for n in numbers:
            prefix='repos/astral-sh/'+repo+'/pulls/'+str(n)
            meta=api([prefix]); fs=[r for page in api(['--paginate','--slurp',prefix+'/files?per_page=100']) for r in page]
            comparisons[repo+'#'+str(n)]={'title':meta['title'],'head':meta['head']['sha'],'state':meta['state'],
                'files':{r['filename']:{'head_blob':r['sha'],'patch_sha256':hashlib.sha256(r.get('patch','').encode()).hexdigest()} for r in fs}}
    ledger={'branches':branches,'prs':prs,'source':source,'released_and_qualified':extra,'ruff':ruff_files,'historical_changed_files':historical,
        'historical_parent':prior,'benchmark_manifest_uses':member_refs,'benchmark_src_and_build_script':resources,'comparisons':comparisons}
    index={}; lines=[]; files={}
    for oid,data in sorted(raw.items()):
        ids=[]
        for line in data.decode().splitlines(keepends=True):
            if line not in index:
                index[line]=len(lines); lines.append(line)
            ids.append(index[line])
        files[oid]=ids
    def write(name,obj):
        body=(json.dumps(obj,sort_keys=True,separators=(',',':'))+'\n').encode()
        (dest/name).write_bytes(gzip.compress(body,compresslevel=9,mtime=0))
    write('head-files.json.gz',ledger)
    write('git-blobs.json.gz',{'lines':lines,'files':files})
    print('verified Git blobs',len(raw),'distinct heads',len(tips))


if __name__=='__main__':main()
