"""Reconstruct and hash every source blob, then check the manifest and compiler rules."""
import argparse
import copy
import gzip
import hashlib
import json
from pathlib import Path
import re
import tomllib

M='crates/ruff_benchmark/Cargo.toml'
CHANGE='b647f3fba81128ae586058b6c0937a3e03c1a997'
HEAD='93526150df078af7dd8fc4226cdcc469539d2001'
RC='235f9228651b74c591e6f62cae4c9b761448dd2d'
RELEASE='7caf39914da1e28a67744ecbc963a5f26361474d'
HEAD_DIGEST='d3fa179a5bdec11dc0e14410dd226234413550b9abfa1e65f16ef705fcee3ef6'


def digest(b): return hashlib.sha256(b).hexdigest()


def verify(ledger, corpus):
    lines=corpus['lines']
    assert len(lines)==len(set(lines))
    blobs={}
    for oid,ids in corpus['files'].items():
        assert all(type(i) is int and 0<=i<len(lines) for i in ids)
        text=''.join(lines[i] for i in ids)
        raw=text.encode()
        assert hashlib.sha1(b'blob '+str(len(raw)).encode()+b'\0'+raw).hexdigest()==oid,oid
        blobs[oid]=text
    heads=sorted(set(ledger['branches'].values())|{p['head'] for p in ledger['prs'].values()})
    assert len(ledger['branches'])==286 and len(ledger['prs'])==230 and len(heads)==290
    assert all(p['state'] in ('closed','open') for p in ledger['prs'].values())
    assert digest(('\n'.join(heads)+'\n').encode())==HEAD_DIGEST
    assert heads==sorted(ledger['source'])
    evidence=set(); fps=set(); mfs=set()
    for h,a in ledger['source'].items():
        if not a:
            evidence.add(h)
            continue
        fb=[b for p,b in a.items() if p.endswith('/fingerprint/mod.rs')]
        mb=[b for p,b in a.items() if p.endswith('/manifest.rs')]
        assert len(a)==2 and len(fb)==len(mb)==1,h
        fps.update(fb); mfs.update(mb)
        f,m=blobs[fb[0]],blobs[mb[0]]
        assert re.search(r'target:\s*(?:util::)?hash_u64\(&unit\.target\)',f),h
        assert re.search(r'#\[derive\([^\]]*?\bHash\b[^\]]*\)\]\s*pub struct Target\s*\{',m),h
        inner=re.search(r'#\[derive\(([^\]]*)\)\]\s*struct TargetInner\s*\{([^}]+)\}',m)
        assert inner and 'Hash' in inner[1] and 'tested: bool' in inner[2],h
    assert len(evidence)==13 and len(fps)==69 and len(mfs)==10
    assert {b for name,b in ledger['branches'].items() if 'evidence' in name and b in evidence}==evidence
    assert not evidence.intersection(p['head'] for p in ledger['prs'].values())
    rel=ledger['released_and_qualified'][RELEASE]; rc=ledger['released_and_qualified'][RC]
    for impl in (rel,rc):
        m=blobs[impl['src/workspace/manifest.rs']]
        assert 'tested: true,' in m and 'test: self.tested(),' in m
        parser=blobs[impl['src/workspace/parser/targets.rs']]
        assert '.set_tested(toml.test.unwrap_or_else(|| t2.tested()))' in parser
        sel=blobs[impl['src/ops/cargo_compile/unit_generator.rs']]
        assert re.search(r'UserIntent::Test\s*=>\s*targets\s*\.iter\(\)\s*\.filter\(\|t\| t\.tested\(\) \|\| t\.is_example\(\)\)',sel)
        assert re.search(r'UserIntent::Build\s*\| UserIntent::Check\s*\{ \.\. \} => targets\s*\.iter\(\)\s*\.filter\(\|t\| t\.is_bin\(\) \|\| t\.is_lib\(\)\)',sel)
        cc=blobs[impl['src/compiler/mod.rs']]
        assert 'let test = unit.mode.is_any_test();' in cc and 'if test && unit.target.harness()' in cc and '.tested()' not in cc
        out=blobs[impl['src/compiler/build_runner/compilation_files.rs']]
        assert 'unit.target.name().hash(&mut shared_hasher);' in out and 'unit.target.kind().hash(&mut shared_hasher);' in out
        assert '.tested()' not in out and 'unit.target.hash(' not in out
        fp=blobs[impl['src/compiler/fingerprint/mod.rs']]
        assert re.search(r'if self\.target != old\.target \{\s*return DirtyReason::TargetConfigurationChanged;',fp)
    assert ledger['historical_changed_files']==[M]
    parent=ledger['historical_parent']
    assert parent=='82e69ebf230eb5206bac5470a37bd34a3a21a9dc'
    prior=blobs[ledger['ruff'][parent][M]].encode()
    child=blobs[ledger['ruff'][CHANGE][M]].encode()
    current=blobs[ledger['ruff'][HEAD][M]].encode()
    needle=b'\ntest = false\n'
    assert child.count(needle)==current.count(needle)==1 and child.replace(needle,b'\n')==prior
    revert=current.replace(needle,b'\n')
    assert digest(current)=='b78ece7fa36c862062b7600d61fb1a411489309ed5e7a367ad3185d09ba88f5b'
    assert digest(revert)=='c51882749d847cc761e096c31aee40ced48942585a9cb57fc2cd67467c44afd2'
    c=tomllib.loads(current.decode()); p=tomllib.loads(revert.decode())
    assert c['lib'].pop('test') is False and c==p
    crate=tomllib.loads(blobs[ledger['ruff'][HEAD]['Cargo.toml']])
    assert crate['workspace']['members']==['crates/*'] and 'default-members' not in crate['workspace']
    assert len(ledger['benchmark_manifest_uses'])==1 and M in ledger['benchmark_manifest_uses'][0]
    assert not any(f.endswith('/build.rs') for f in ledger['benchmark_src_and_build_script'])
    rsrc=blobs[ledger['ruff'][HEAD]['crates/ruff_benchmark/src/lib.rs']]
    includes=re.findall(r'include_str!\("([^"]+)"\)',rsrc)
    assert len(includes)==5 and '../resources/pydantic/types.py' in includes
    prs=ledger['comparisons']; assert set(prs)==set(['ohm-cargo#161','ohm-cargo#263','ohm-cargo#268','ohm-cargo#275','ohm-cargo#276','ohm-rust#25','ohm-rust#58'])
    assert 'src/compiler/ohm_deferred_dev_deps.rs' in prs['ohm-cargo#161']['files']
    assert 'src/ops/resolve.rs' in prs['ohm-cargo#275']['files']
    assert 'src/resolver/resolve.rs' in prs['ohm-cargo#276']['files']
    for pr in ('ohm-cargo#161','ohm-cargo#268','ohm-cargo#275','ohm-cargo#276'):
        assert not any(f.endswith('/fingerprint/mod.rs') for f in prs[pr]['files'])
    return len(blobs), len(heads)-len(evidence)


def rejects(check):
    try: check()
    except AssertionError: return
    raise AssertionError('tampering passed')


def main():
    cli=argparse.ArgumentParser(description=__doc__)
    cli.add_argument('--mutations',action='store_true')
    opt=cli.parse_args()
    root=Path(__file__).resolve().parent
    def load(name):
        return json.loads(gzip.decompress((root/'snapshot'/name).read_bytes()))
    rows=load('head-files.json.gz');data=load('git-blobs.json.gz')
    n,h=verify(rows,data)
    prior=json.loads((root/'snapshot/prior-capture.json').read_bytes())
    branches=dict(rows['branches'])
    assert branches[prior['ref']]==prior['new']
    branches[prior['ref']]=prior['old']
    previous=sorted(set(branches.values())|{p['head'] for p in rows['prs'].values()})
    assert digest(('\n'.join(previous)+'\n').encode())==prior['prior_heads_sha256']
    assert len(prior['paths'])==prior['count']==16
    assert all(p.startswith('benchmarks/') for p in prior['paths'])
    assert prior['prior_product_heads']==h
    if opt.mutations:
        mutated=copy.deepcopy(rows);mutated['source'].pop(RC)
        rejects(lambda:verify(mutated,data))
        mutated=copy.deepcopy(rows);mutated['historical_changed_files'].append('src/lib.rs')
        rejects(lambda:verify(mutated,data))
        altered=dict(data);altered['lines']=list(data['lines']);altered['lines'][0]+='x'
        rejects(lambda:verify(rows,altered))
    print(f'{n} full Git blobs verified. {h} of {h} published product heads retain the same ordinary target hash. Historical and current single-line edits verified.')


if __name__=='__main__':main()
