#!/usr/bin/env python3
"""Verify the release identities and read both sets of actual Cargo verdicts independently."""
import copy
import gzip
import hashlib
import json
from pathlib import Path
import re
import sys

BASE=Path(__file__).resolve().parent
TAG="ohm-1.99.0-19"
TRIPLE="x86_64-unknown-linux-gnu"
ARCHIVE=f"{TAG}-{TRIPLE}.tar.gz"
HASH="ef21d83519bc376479811a7e01fa5ac8915ac0a500c6859bc22a1e0b4913d812"
RUST="eef2f3425c1c6f7fddfb4555769a9f90fe1e0f53"
CARGO="235f9228651b74c591e6f62cae4c9b761448dd2d"
FIX="34dad66fd2ac823bfb02c2c4a4bab02fb5ac4d31"
CODES={"cargo":"789c2f116732ed642565d0f92c500838f8cd53664fbe60f205a5621c43cbecf1","rustc":"5694abe50767a22cebeccb767143f7404d5e81c4b1760cff4426466bf410e511","rustdoc":"a368ad0fdc5a72d5832d0425c00ee41cf1368908eae4835d303262dd8b266cf0","driver":"f772b49abec18759edbd9cb7f9f2930097d6ba64d9a2b82837edf4451acc3014","wild":"0d6335808b647d499f3d74993b602e64ff0625206c809bf4913c487eea380cd5"}
ORDERS=("provider-first","provider-late")
PHASES=("original","original-repeat","edited","edited-repeat","edited-clean","restore","restore-repeat")
CRATES={"api","provider","reader","client"}
E0034="f56ad66c2eeaeee09d18d874b7c52f8929edc44bdef3c993ce34c380741dde56"
def h(b):
    return hashlib.sha256(b).hexdigest()
def ledger(p):
    rows=[line.split(maxsplit=1) for line in p.read_text().splitlines()]
    assert len({n for _,n in rows})==len(rows)
    return {n:d for d,n in rows}
def read_gz(name):
    return json.loads(gzip.decompress((BASE/name).read_bytes()))
def check_release(item):
    assert item['tag']==TAG and item['platform']==TRIPLE and item['published_at']=='2026-10-29T06:41:55Z'
    assert item['assets'][ARCHIVE]=={'sha256':HASH,'bytes':359628600}
    assert item['archive_sidecar']==HASH and {k:v['sha256'] for k,v in item['images'].items()}==CODES
    assert set(item['images'])==set(CODES)
    for k,rec in item['images'].items():
        assert rec['archive_member'].startswith('rust-1.99.0-dev-'+TRIPLE+'/'+('cargo/' if k=='cargo' else 'rustc/'))
        assert rec['bytes']>0
    assert all('commit-hash: '+rev+'\n' in item['versions'][k] and TAG in item['versions'][k] for k,rev in [('rustc',RUST),('cargo',CARGO)])
    public=ledger(BASE/'release/SHA256SUMS.asset')
    side=ledger(BASE/('release/'+ARCHIVE+'.sha256'))
    assert side=={ARCHIVE:HASH} and item['assets']['SHA256SUMS']['sha256']==h((BASE/'release/SHA256SUMS.asset').read_bytes())
    assert all(item['assets'][n]['sha256']==v for n,v in public.items())
    m=BASE/('release/'+TAG+'.json')
    assert h(m.read_bytes())==public[TAG+'.json'] and item['manifest']==json.loads(m.read_bytes())
    assert item['manifest']['sources']['rust']['revision']==RUST and item['manifest']['sources']['cargo']['revision']==CARGO
    assert item['manifest']['release']['ohm_revision']==19
    assert item['manifest']['bundled_tools']['wild']=={'sha256':'25012a78de164686f552b7703b5d0223adab4829c79cd1fb351108221d61c7d8','version':'0.11.0'}

def check_joint(official,qa,streams):
    check_release(official['release'])
    cite=official['source_packets']
    for family in ('trait','revert','fixed'):
        folder=BASE/('fixed-qa' if family=='fixed' else family)
        mf=folder/'SHA256SUMS.reference';assert h(mf.read_bytes())==cite[family]
        orig=ledger(mf)
        if family=='fixed':
            assert cite[family]=='54f63217c50e2c77349e932aff33e7c0f620dedf31d2b386e6eaf12aa13d41ef'
            assert h(gzip.decompress((folder/'outcomes.json.gz').read_bytes()))==orig['outcomes.json']
            assert h((folder/'raw-ledger.json').read_bytes())==orig['raw-ledger.json']
        else:
            kept={n for n in orig if n in ('reproduce.py','commit-order.c') or n.startswith(('fixture/','wrapper/'))}
            assert kept=={str(p.relative_to(folder)) for p in folder.rglob('*') if p.is_file() and p!=mf}
            assert all(h((folder/n).read_bytes())==orig[n] for n in kept)
    assert {k for k in streams}=={o+'/'+s+'.'+t for o in ORDERS for s in PHASES for t in ('stderr','stdout')}
    assert set(official['check'])==set(ORDERS)
    anchors=qa['subjects']
    assert anchors['cargo_source']==FIX and anchors['rust']==RUST and anchors['wild']==CODES['wild']
    assert anchors['cargo']=='a9c1b18bbb02f541bcf089db9d4286c215ffc8036fa1ff443e59c9210e77771c'
    assert anchors['frontend']!=CODES['rustc'] and anchors['driver']!=CODES['driver']
    assert len(anchors['target_files'])==53
    error_hashes=set()
    for order in ORDERS:
        case=official['check'][order]
        assert set(case['phases'])==set(PHASES) and h(case['worker_stdout'].encode())==case['worker_stdout_sha256']
        assert case['worker_stderr']=={'bytes':0,'sha256':h(b'')}
        events=case['events']; held='provider' if order=='provider-late' else 'reader'
        assert [(e['event'],e['crate'],e['restore']) for e in events if e['event'].startswith(('hold','release','error','timeout'))]==[('hold-fd',held,0),('release-fd',held,0)]
        assert all(e['observed_ns']==e['requested_ns'] for e in events if e['event']=='after-fd')
        assert bool([e for e in events if e['event']=='after-fd' and e['crate']!=held])
        assert case['interposer']['sha256']=='a2ea0700d7389255e1b9270ec844f034d48742b29551d0e284d4dc70835480c1'
        source=ledger(BASE/'trait/SHA256SUMS.reference')
        assert all(source['fixture/'+k]==v['sha256'] for k,v in case['sources'].items())
        assert set(case['sources'])=={k.removeprefix('fixture/') for k in source if k.startswith('fixture/')}
        state=case['state']
        assert state['restored']['provider']['public_api']['value']!=state['edited-clean']['provider']['public_api']['value']
        assert state['restored']['reader']['public_api']['value']==state['edited-clean']['reader']['public_api']['value']
        q=qa['e0034'][order]
        assert q['verdict']=='correct' and all(q['physical_checks'].values())
        fixes={p['phase']:p for p in q['cargo']}
        assert set(fixes)==set(PHASES)
        for phase in PHASES:
            r=case['phases'][phase]
            emitted=streams[order+'/'+phase+'.stdout']
            for ext in ('stdout','stderr'):
                b=streams[order+'/'+phase+'.'+ext].encode();m=r['streams'][ext]
                assert h(b)==m['portable_sha256'] and b.count(b'@RELEASE_REPLAY@')==m['local_root_replacements']
                if m['local_root_replacements']==0:assert m['bytes']==len(b) and m['sha256']==h(b)
            messages=[json.loads(line) for line in emitted.splitlines()]
            fail=phase=='edited-clean' or (order=='provider-first' and phase in ('edited','edited-repeat'))
            require_fixed_error=phase in ('edited','edited-repeat','edited-clean')
            assert r['exit']==(101 if fail else 0)
            assert messages[-1]=={'reason':'build-finished','success':not fail}
            arts={x['target']['name']:x['fresh'] for x in messages if x['reason']=='compiler-artifact'}
            assert r['artifacts']==arts
            if phase in ('original-repeat','restore-repeat') or (order=='provider-late' and phase=='edited-repeat'):
                assert arts==dict.fromkeys(CRATES,True)
            if phase=='original':assert arts==dict.fromkeys(CRATES,False)
            if phase=='edited-clean':assert arts==dict.fromkeys(CRATES-{'client'},False)
            errs=[x for x in messages if x['reason']=='compiler-message' and x['message']['level']=='error']
            assert len(errs)==len(r['errors'])==int(fail)
            assert len(fixes[phase]['errors'])==int(require_fixed_error)
            assert fixes[phase]['finished']['success'] is not require_fixed_error
            if require_fixed_error:
                e,=fixes[phase]['errors']; assert (e['crate'],e['code'],e['span'])==('client','E0034',3)
                error_hashes.add(e['rendered_sha256'])
            if fail:
                diag=errs[0]['message'];e,=r['errors']
                assert e['target']==errs[0]['target']['name']=='client'
                assert e['code']==diag['code']['code']=='E0034' and e['summary']==diag['message']=='multiple applicable items in scope'
                assert e['primary']==[[s['file_name'],s['line_start'],s['column_start']] for s in diag['spans'] if s['is_primary']]==[['client/src/main.rs',3,30]]
                assert e['notes']==[x['message'] for x in diag['children'] if x['level']=='note'] and all(any(token in x for x in e['notes']) for token in ('`First`','`Second`'))
                assert e['rendered_sha256']==h(diag['rendered'].encode())
                error_hashes.add(e['rendered_sha256'])
    assert error_hashes=={E0034}
    s=official['revert'];z=s['result']
    assert s['first_stdout']==s['final_stdout']=='1\n'
    assert z['rustc_sha256']==CODES['rustc'] and z['cargo_sha256']==CODES['cargo']
    assert z['value']==1 and z['first_success']=='untouched-1' and s['retained_markers']=={'early':'ready','failed':'failed'}
    assert set(s['phases'])==set(z['phases'])=={'make-wrapper','prime','prime-program','forced-failure','reverted','untouched-1','final-program'}
    for name,r in s['phases'].items():
        assert z['phases'][name]=={k:v for k,v in r.items() if k!='native'}
        assert r['rustcs']==[[v['crate'],v['crate_type']] for v in r['native']]
        assert all(re.fullmatch('[a-f0-9]{64}',v['literal_sha256']) for v in r['native'])
        assert r['exit']==(101 if name in ('forced-failure','reverted') else 0)
        assert r['errors']==(['E0460'] if name=='reverted' else [])
        if name in ('prime-program','final-program'):assert r['files']['stdout']==h(b'1\n')
    assert s['phases']['forced-failure']['rustcs']==[['dep','lib'],['app','lib']]
    assert s['phases']['reverted']['rustcs']==[['dep','lib'],['app','bin']]
    assert s['phases']['untouched-1']['rustcs']==[['app','lib'],['app','bin']]
    assert s['elfs']['program']=={'sha256':'0dfe4722bb9ea05666b511d5282a0ca6cf4eb869904c206850e6eebcdf8a94c8','bytes':436648}
    for family in ('source','wrapper_source'):
        prefix='fixture/' if family=='source' else 'wrapper/'
        ref=ledger(BASE/'revert/SHA256SUMS.reference')
        assert set(s[family])=={k[len(prefix):] for k in ref if k.startswith(prefix)}
        assert all(ref[prefix+k]==v['sha256'] for k,v in s[family].items())
    fixed=qa['wrapped_recovery']['detail']
    assert fixed['first_success']=='reverted' and fixed['phases']['reverted']['rustcs']==[['dep','lib'],['app','lib'],['app','bin']]
    assert fixed['phases']['reverted']['exit']==0 and not fixed['phases']['reverted']['errors'] and fixed['value']==1
    return True

def check_revert_streams(official,streams):
    assert set(streams)==set(official["revert"]["phases"])
    for phase,items in streams.items():
        r=official["revert"]["phases"][phase]
        assert set(items)=={"stdout","stderr"}
        for name,item in items.items():
            b=item["text"].encode()
            assert item["raw_sha256"]==r["files"][name] and item["portable_sha256"]==h(b)
            assert item["local_root_replacements"]==b.count(b"@RELEASE_REPLAY@")
            if not item["local_root_replacements"]:assert h(b)==item["raw_sha256"] and len(b)==item["bytes"]
        assert re.findall(r"error\[(E[0-9]+)\]",items["stderr"]["text"])==r["errors"]
        if phase in ("prime-program","final-program"):assert items["stdout"]["text"]=="1\n"

if __name__=="__main__":
    official=json.loads((BASE/"official.json").read_bytes())
    fixed=read_gz("fixed-qa/outcomes.json.gz")
    streams=read_gz("cargo-streams.json.gz")
    assert check_joint(official,fixed,streams)
    check_revert_streams(official,read_gz("revert-streams.json.gz"))
    if "--selftest" in sys.argv:
        def reject(change):
            sample=copy.deepcopy(official);change(sample)
            try:check_joint(sample,fixed,streams)
            except AssertionError:return
            raise AssertionError("Accepted corrupt evidence")
        reject(lambda d: d["release"]["images"]["cargo"].update(sha256=fixed["subjects"]["cargo"]))
        reject(lambda d: d["check"]["provider-late"]["phases"]["edited"].update(exit=101))
        reject(lambda d: d["check"]["provider-first"]["phases"]["edited-clean"]["errors"].clear())
        reject(lambda d: d["check"]["provider-late"]["events"].clear())
        reject(lambda d: d["revert"]["result"].update(first_success="reverted"))
        reject(lambda d: d["revert"]["phases"]["reverted"]["native"].clear())
        print("Rejected six altered release, ordering, diagnostic and compiler witnesses.")
    print("Verified five official ELF identities, 14 released and 14 fixed checks, both first-revert outcomes, native programs and complete Cargo streams.")
