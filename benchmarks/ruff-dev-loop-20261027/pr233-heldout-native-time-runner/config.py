"""Pinned versions, isolated physical paths and compact reference receipts for the H5 wall study."""
from collections import Counter
from pathlib import Path
import hashlib, json, os, platform, shutil, sys

HERE = Path(__file__).resolve().parent
BASE = Path.home()/'.cache/ohm-233-position-qualified-20261027'
QUAL = BASE/'pr233-three-parser-protocol-h5-v2'
ORIGIN = BASE/'first-occurrence-classic-pr233-h5-v2'
sys.path.insert(0, str(QUAL))
from common import P, PIN, RUFF, FROZEN, CARGO_HOME, SONAME, load, dump, need, sha
from novel_state import PLAN as SOURCE, verify_plan
from witness import as_digest
from state import source_clean
ARENA = P/'pr233-time-run-v1'
BOUND = load(QUAL/'binding.json')
PLAN = load(HERE/'time-plan.json')
PLAN_SHA = '67580e3a837c0cee6bd8ab9a2178e58106f9174ed4788a2e627fe9818fc6515b'
PREREG = 'f30159902713010f7d81f05c72a38ee9e3e7e4e0'
RELEASE = BASE/'pr233-time-control-v1'

def capacity():
    available = {str(p):shutil.disk_usage(p).free for p in (P, BASE)}
    need(min(available.values()) >= 25 * 2**30, ('25 GiB reserve', available))
    return available

def validate_host():
    need(not sys.flags.optimize and platform.node()=='charlie-ohm-loader-perf-1024' and platform.machine()=='x86_64', 'host')
    need(platform.release()==BOUND['host']['kernel'] and os.cpu_count()==32 and list(sorted(os.sched_getaffinity(0)))==list(range(24)), 'CPU affinity / kernel')
    need(shutil.which('cargo')==str(Path.home()/'.cargo/bin/cargo'), 'cargo rustup proxy')
    need(set(os.environ)<=set('HOME PATH LANG LC_ALL USER LOGNAME'.split()), ('unexpected environment', sorted(os.environ)))
    need(sha(HERE/'time-plan.json')==PLAN_SHA and sha(QUAL/'binding.json')==PLAN['qualified_binding_sha256'], 'published timing and subject identities')
    need(PLAN['ruff']==PIN and len(PLAN['sequence'])==96 and len(PLAN['endpoints'])==6, 'schedule')
    for line in (HERE/'SHA256SUMS').read_text().splitlines():
        digest,name=line.split('  ',1)
        need(sha(HERE/name)==digest,('changed clock runner',name))
    for name,digest in BOUND['runner'].items():
        need(sha(QUAL/name)==digest,('changed qualified input',name))
    verify_plan()
    for a in 'BC':
        for field in ('cargo','driver'):
            ref=BOUND['arms'][a]
            need(sha(Path(ref[field]))==ref[field+'_sha256']==(PLAN['cargo_sha256'] if field=='cargo' else PLAN['arms'][a]['driver']), ('selected release',a,field))
    for k,rec in BOUND['host']['host_tools'].items():
        need(Path(rec['path']).resolve()==Path(rec['resolved']) and sha(Path(rec['path']))==rec['sha256'],('host tool',k))
    need(BOUND['host']['host_tools']['Wild']['sha256']==PLAN['wild_sha256'], 'Wild')
    need(source_clean()==BOUND['host']['source_index_sha256'], 'real Ruff checkout / index')
    capacity()

def native_expected(receipt):
    return dict(jobs=sorted([r['crate'],r['kind']] for r in receipt['processes']['jobs']),
                native=receipt['native_totals'])

def expected(mode,arm,name):
    f=ORIGIN/'receipts'/mode/arm/name/'receipt.json'
    rec=load(f);prod=rec['product']
    return dict(source_view=rec['source_view'], units=rec['unit_count'], roster=prod['structural_roster'],
                release_roster=rec['release_output_roster'], messages=prod['messages'],dirty=prod['dirty'],
                elf=sorted(prod['elf']), exes=rec['executable_count'], old_cli=prod['diagnostics'],
                novel_cli=rec['novel_cli'], native=native_expected(rec), original_receipt=sha(f))

def verify_origin():
    done=load(ORIGIN/'complete.json')
    need((BASE/'pr233-h5-control-v2/exit.txt').read_text().strip()=='0' and done['test_admitted'] and done['source_index_unchanged']==BOUND['host']['source_index_sha256'], 'independent completed source control')
    refs={}
    for m in ('build','test'):
        obs=ORIGIN/(m+'-observations.json')
        need(sha(obs)==load(ORIGIN/(m+'-complete.json'))['result_sha256'],('descriptive evidence',m))
        for a in 'BC':
            state=ORIGIN/'state'/m/a
            need((state/'source-state').read_text()=='original' and state.stat().st_dev!=P.stat().st_dev,('distinct ext4 source store',m,a))
            for n in ['original-baseline',*[e+'-'+direction for e in SOURCE['schedule'] for direction in ('edit','restore')]]:
                key='/'.join((m,a,n));refs[key]=expected(m,a,n)
                fr=load(ORIGIN/'receipts'/m/a/(n+'-fresh')/'receipt.json')
                need(fr['fresh_units']==fr['unit_count'] and not fr['processes']['jobs'] and not any(fr['native_totals'].values()) and fr['release_output_roster']==refs[key]['release_roster'] and fr['product']['messages']==refs[key]['messages'],('original immediate native control',key))
    for m in ('build','test'):
        for n in ['original-baseline',*[e+'-'+direction for e in SOURCE['schedule'] for direction in ('edit','restore')]]:
            a,b=(refs['/'.join((m,arm,n))] for arm in 'BC')
            need(all(a[k]==b[k] for k in ['release_roster','messages','old_cli','novel_cli','elf','exes']),('comparison subject',m,n))
    return refs
