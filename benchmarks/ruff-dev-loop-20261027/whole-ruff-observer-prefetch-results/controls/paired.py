"""Whole Cargo native builds with stable logical paths and a separate exec audit."""
import argparse
import ast
import gzip
import hashlib
import itertools
import json
import math
import os
from pathlib import Path
import re
import shutil
import statistics
import subprocess
import time

HERE = Path(__file__).resolve().parent
NAMES = ('hold_direct', 'hold_indirect', 'hold_plain')
ARM = {'P': 'parent', 'C': 'candidate'}
FILE = Path('hold_shapes/src/types.rs')
OLD = b'/// One private shape\n'
NEW = b'/// One private shapes\n'
MARK = b'ohm-foreign-span-bytes'
PLAN = HERE / 'cooperating-plan.json'
EXPECTED_PLAN = 'f169b2d0ffcdf3caf531ab2bd1fe39409f65cefe379544f13e3d61f68aad1b06'
FIX = HERE / 'heldout-fixture'
MANIFEST = HERE / 'heldout-fixture-sha256.json'

def sha(path):
    with path.open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()

def log_json(path, value):
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + '\n')

def paths_digest(root):
    return {str(p.relative_to(root)): sha(p) for p in sorted(root.rglob('*')) if p.is_file() and p.name != 'Cargo.lock'}

def save_text(path, data):
    path.write_bytes(gzip.compress(data, compresslevel=5, mtime=0))

def roster(raw):
    pending, completed = {}, []
    for line in raw.decode(errors='replace').splitlines():
        pid, _, rest = line.partition(' ')
        if '<unfinished ...>' in rest:
            pending[pid] = rest.split('<unfinished ...>')[0]
        elif 'execve resumed>' in rest:
            completed.append(pending.pop(pid, '') + rest.split('resumed>', 1)[1])
        else:
            completed.append(rest)
    result, images = [], []
    for line in completed:
        if not line.startswith('execve("') or not re.search(r'= 0$', line):
            continue
        name = ast.literal_eval(re.match(r'execve\(("(?:[^"\\]|\\.)*")', line)[1])
        images.append(name)
        crate = re.search(r'"--crate-name", "([^"]+)"', line)
        if not crate or crate[1] in ('___', '__') or not name.endswith('/bin/rustc'):
            continue
        result.append({'crate': crate[1], 'mode': 'relink' if 'link-only' in line else 'full',
                       'capture': '-Zbinary-dep-depinfo' in line, 'checksum': 'checksum-hash-algorithm' in line})
    return sorted(result, key=lambda x: x['crate']), images

class Study:
    def __init__(self, args):
        self.a = args
        self.root = args.work.resolve()
        self.root.mkdir()
        self.active = self.root / 'active'
        self.active.mkdir()
        self.logs = self.root / 'results'
        self.logs.mkdir()
        self.bins = {'C': args.candidate.resolve(), 'P': args.parent.resolve()}
        self.state = args.state.resolve() if args.state else (Path('/mnt/devbox-scratch/dev-user/ohm-nonleaf-perflint-20261026/stage-score') if args.stage1 else Path.home() / '.cache/ohm-ruff-packed-edges-20261026/nonleaf/trait-pgo-state')
        self.tc = self.state / 'sysroot'
        self.driver = args.driver.resolve()
        self.driver_name = next((self.tc / 'lib').glob('librustc_driver*.so')).name
        self.src = FIX.resolve()
        self.source_hashes = paths_digest(self.src)
        assert sha(PLAN) == EXPECTED_PLAN
        assert sha(MANIFEST) == '1a309c176ba8ea129414be486ce87a040c171d294e9d12a5388bdaaa94d6f78e'
        assert self.source_hashes == json.loads(MANIFEST.read_text())
        self.gold = {}
        self.results = {}
        self.proxy = str(Path.home() / '.cargo/bin/cargo')
        self.digest = {key: sha(v) for key, v in {**self.bins, 'rustc': self.tc / 'bin/rustc', 'driver': self.driver}.items()}
        log_json(self.logs / 'subject.json', {'sha256': self.digest, 'resolved': {**{k:str(v) for k,v in self.bins.items()}, 'driver':str(self.driver), 'rustc':str(self.tc/'bin/rustc')}, 'physical': str(self.root), 'logical':str(self.active), 'state':str(self.state),'affinity':args.cpus,'plan':sha(PLAN), 'source_manifest':sha(MANIFEST), 'mode':args.mode,'untimed_tracing':True})
    def init(self, label):
        path = self.root / label
        path.mkdir()
        shutil.copytree(self.src, path/'src')
        for sub in ('target', 'shared', 'cargo-home'):
            (path / sub).mkdir()
        return path
    def edit(self, arm, new):
        f = arm/'src'/FILE
        value = f.read_bytes()
        if new == bool(NEW in value):
            return
        assert value.count(OLD if new else NEW) == 1
        f.write_bytes(value.replace(OLD if new else NEW, NEW if new else OLD))
    def proof_files(self, arm):
        signed = {}
        for f in itertools.chain((arm/'shared').rglob('dep-*'), (arm/'target').rglob('dep-*')):
            if not f.is_file():
                continue
            data = f.read_bytes()
            if MARK in data:
                pos = data.rfind(b'OBS1')
                sign = None if pos == -1 else data[pos+4:].hex()
                signed[str(f.relative_to(arm))] = {'bytes':len(data),'trailer':sign,'complete': None if pos == -1 else (data[pos+8] == 1),'signed':pos != -1 and len(data)-pos == 41,'sha256':hashlib.sha256(data).hexdigest()}
        return signed
    def run(self, arm, binary, name, *, trace=False, packages=NAMES, extra=(), envadd=None, mode='build', check_product=True, expect=True):
        logs = self.logs/name; logs.mkdir()
        env = {k:v for k,v in os.environ.items() if not k.startswith(('RUSTC','RUSTUP_','CARGO_')) and k not in ('RUSTFLAGS','LD_LIBRARY_PATH','BASH_ENV')}
        env.update(RUSTUP_HOME=str(self.state/'rustup'), RUSTUP_AUTO_INSTALL='0',
                   CARGO_HOME=str(self.active/'cargo-home'), CARGO_BUILD_JOBS='4',
                   CARGO_TARGET_DIR=str(self.active/'target'), CARGO_BUILD_BUILD_DIR=str(self.active/'shared'),
                   GIT_OPTIONAL_LOCKS='0', CARGO_TERM_COLOR='never')
        env.update(envadd or {})
        ns = ['taskset','-c',self.a.cpus,'bwrap','--ro-bind','/','/','--dev','/dev','--proc','/proc',
              '--tmpfs','/tmp','--bind',str(self.root),str(self.root),'--bind',str(arm),str(self.active),
              '--ro-bind',str(self.driver),str(self.tc/'lib'/self.driver_name),
              '--ro-bind',str(self.bins[binary]),str(self.tc/'bin/cargo'),'--chdir',str(self.active/'src'),'--']
        args = [self.proxy,'+ohm',*extra,*mode.split(),'--offline',*itertools.chain.from_iterable(('-p',n) for n in packages)]
        cmd = ns + (['strace','-f','-qq','-s','8192','-e','trace=execve','-o',str(logs/'exec')] if trace else []) + args
        start = time.monotonic_ns()
        proc = subprocess.run(cmd, env=env, capture_output=True)
        elapsed = time.monotonic_ns() - start
        save_text(logs/'stdout.gz',proc.stdout); save_text(logs/'stderr.gz',proc.stderr)
        rr, images = [], []
        if trace:
            f=logs/'exec'
            raw=f.read_bytes(); rr,images=roster(raw); save_text(logs/'exec.gz',raw); f.unlink()
        products = {}
        if proc.returncode == 0 and check_product:
            for n in NAMES:
                p=arm/'target/debug'/n
                if p.is_file():
                    products[n]={'output':subprocess.check_output([str(p)],text=True,timeout=10).strip(),'sha256':sha(p)}
        row={'arm':binary,'phase':name,'source':sha(arm/'src'/FILE),'ns':elapsed,'timed':not trace,
             'status':proc.returncode,'argv':args,'native_products':products,'readers':self.proof_files(arm),
             'roster':rr,'successful_exec_images':images}
        self.results[name] = row
        log_json(logs/'result.json',row)
        if expect and proc.returncode:
            print(proc.stderr.decode(errors='replace'),flush=True)
            raise RuntimeError(f'{name} failed, see {logs}')
        if trace:
            print(name,[(x['crate'],x['mode'],x['capture']) for x in rr], {k:v['output'] for k,v in products.items()},[v['trailer'] for v in row['readers'].values()],flush=True)
        return row
    def equivalent(self, row, gold, require_elf=True):
        assert set(row['native_products']) == set(NAMES)
        for n in NAMES:
            x,y=row['native_products'][n],gold['native_products'][n]
            assert x['output']==y['output'], (row['phase'],gold['phase'],n,x,y)
            if require_elf: assert x['sha256']==y['sha256'], (row['phase'],gold['phase'],n,x,y)
    def references(self):
        for new in (False,True):
            arm=self.init('empty-'+str(int(new)))
            self.edit(arm,new)
            self.gold[new]=self.run(arm,'P','empty-'+str(int(new)),trace=True)
        for n in ('hold_direct','hold_indirect'):
            assert self.gold[False]['native_products'][n]['output']!=self.gold[True]['native_products'][n]['output']
        assert self.gold[False]['native_products']['hold_plain']['output']==self.gold[True]['native_products']['hold_plain']['output']
    def train(self, arms, tag):
        for k,arm in arms.items():
            for i in range(4):
                r=self.run(arm,k,f'{tag}-{k}-{i}',trace=True)
                self.equivalent(r,self.gold[False])
            full={rec['crate'] for rec in r['roster'] if rec['mode']=='full'}
            assert full==({'hold_direct','hold_bridge'} if k=='P' else set()), (k,full)
            if k=='C':
                assert r['roster']==[] and len(r['readers'])>=2 and all(v['complete'] for v in r['readers'].values()),r
    def paired(self, arms, trace):
        tag = 'audit' if trace else 'native'
        for plan in json.loads(PLAN.read_text())['orders']:
            block=plan['block']
            for phase,key in (('noop','no_op'),('edit','edit_order')):
                new=(plan['edit']=='add') if phase=='edit' else (plan['edit']!='add')
                for k in plan[key]:
                    if phase=='edit': self.edit(arms[k],new)
                    r=self.run(arms[k],k,f'{tag}-{block:02d}-{phase}-{k}',trace=trace)
                    self.equivalent(r,self.gold[new])
        if not trace:
            ratios=[math.log(self.results[f'native-{i:02d}-noop-P']['ns']/self.results[f'native-{i:02d}-noop-C']['ns']) for i in range(1,13)]
            orders=json.loads(PLAN.read_text())['orders']
            chronological=[r if p['no_op']=='PC' else -r for r,p in zip(ratios,orders)]
            s=sum(ratios)
            candidates=[sum((1 if i in selected else -1)*x for i,x in enumerate(chronological)) for selected in itertools.combinations(range(12),6)]
            pct=sorted([100*(-math.expm1(-r)) for r in ratios])
            log_json(self.logs/'score.json',{'median_reduction_pct':statistics.median(pct),'paired_median_CI_pct':[pct[2],pct[9]],'favorable':sum(x>0 for x in pct),'raw_one_sided_p':sum(x>=s-1e-12 for x in candidates)/len(candidates),'median_ns':{k:statistics.median(self.results[f'native-{i:02d}-noop-{k}']['ns'] for i in range(1,13)) for k in ARM}})
    def main(self):
        self.references()
        arms={k:self.init('arms-'+k) for k in ARM}
        self.train(arms,'training')
        if self.a.mode == 'preflight':
            for new in (True,False):
                for k,arm in arms.items():
                    self.edit(arm,new)
                    r=self.run(arm,k,f'first-{k}-{int(new)}',trace=True); self.equivalent(r,self.gold[new])
                    r=self.run(arm,k,f'repeat-{k}-{int(new)}',trace=True); self.equivalent(r,self.gold[new])
            return
        self.paired(arms,False)
        audit={k:self.init('audited-arms-'+k) for k in ARM}
        self.train(audit,'audit-training')
        self.paired(audit,True)

def getargs():
    p=argparse.ArgumentParser()
    p.add_argument('--mode',choices=('preflight','score'),default='preflight')
    p.add_argument('--work',type=Path,required=True)
    p.add_argument('--driver',type=Path,required=True)
    p.add_argument('--parent',type=Path,required=True)
    p.add_argument('--candidate',type=Path,required=True)
    p.add_argument('--stage1',action='store_true')
    p.add_argument('--state',type=Path)
    p.add_argument('--cpus',default='0-3')
    return p.parse_args()

if __name__=='__main__':
    Study(getargs()).main()
