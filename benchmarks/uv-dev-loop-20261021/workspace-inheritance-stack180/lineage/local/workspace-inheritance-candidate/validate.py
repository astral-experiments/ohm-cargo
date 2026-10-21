#!/usr/bin/env python3
"""Isolated correctness build and existing workspace inheritance coverage; no performance data."""
import datetime,hashlib,json,os,re,subprocess,sys,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
OUT=Path(__file__).resolve().parent
SOURCE=ROOT/'work/cargo-shared-workspace-dependencies'
TARGET=OUT/'compiler-build'
META=json.loads((OUT/'source.json').read_text())
def now():return datetime.datetime.now(datetime.timezone.utc).isoformat()
def sha(p):
 with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def git(*args,env=None):return subprocess.check_output(['git','-C',str(SOURCE),*args],env=env)
def verify_source():
 assert git('rev-parse','HEAD').decode().strip()==META['head']
 assert git('diff','--binary','--full-index')==(OUT/'share-workspace-dependencies.patch').read_bytes()
 assert sha(SOURCE/'Cargo.lock')==META['cargo_lock_sha256']
 for p,h in META['changed_files'].items():assert sha(SOURCE/p)==h
 assert not git('ls-files','--others','--exclude-standard').strip()
def write_record():
 p=OUT/'validation.json.tmp';p.write_text(json.dumps(record,indent=2)+'\n');p.replace(OUT/'validation.json')
assert not (OUT/'validation.json').exists()
assert not TARGET.exists()
verify_source()
ENV=os.environ.copy()
removed=[]
for k in list(ENV):
 if k.startswith(('CARGO_PROFILE_','CARGO_BUILD_')) or k in ['RUSTFLAGS','CARGO_ENCODED_RUSTFLAGS','RUSTC_WRAPPER','RUSTC_WORKSPACE_WRAPPER','RUSTUP_TOOLCHAIN','CARGO_TARGET_DIR','CARGO_HOME','CARGO_INCREMENTAL','__CARGO_OHM_DEFAULTS','CARGO_LOG','RUST_LOG']:
  removed.append(k);ENV.pop(k)
TOOLS=META['toolchain_tools']
ENV.update(CARGO_HOME='/tmp/codex-cargo-home',CARGO_TARGET_DIR=str(TARGET),CARGO_PROFILE_DEV_DEBUG='0',CARGO_PROFILE_TEST_DEBUG='0',CARGO_INCREMENTAL='0',CFG_RELEASE_CHANNEL='dev',RUSTC=TOOLS['rustc'],RUSTDOC=TOOLS['rustdoc'])
ENV['PATH']=str(Path(TOOLS['rustc']).parent)+os.pathsep+ENV.get('PATH','')
command=['taskset','-c','0-7',TOOLS['cargo'],'test','--locked','--offline','-p','cargo','--test','testsuite','--no-run','-j','8','--message-format=json']
record={'started_at':now(),'status':'building','purpose':'correctness only; default Cargo features and stock1.99; no benchmark','source':META,'runner_sha256':sha(__file__),'command':command,'target_path':str(TARGET),'removed_environment_keys':removed,'environment_overrides':{k:ENV[k] for k in ['CARGO_HOME','CARGO_TARGET_DIR','CARGO_PROFILE_DEV_DEBUG','CARGO_PROFILE_TEST_DEBUG','CARGO_INCREMENTAL','CFG_RELEASE_CHANNEL','RUSTC','RUSTDOC','PATH']},'tool_sha256':{k:sha(v) for k,v in TOOLS.items()},'tool_versions':{k:subprocess.check_output([v,'-vV'] if k!='rustdoc' else [v,'--version'],env=ENV).decode() for k,v in TOOLS.items()},'checks':[]}
write_record()
try:
 with (OUT/'build.jsonl').open('xb') as stdout,(OUT/'build.stderr').open('xb') as stderr:
  result=subprocess.run(command,cwd=SOURCE,env=ENV,stdout=stdout,stderr=stderr,timeout=1800)
 record['build_returncode']=result.returncode;record['build_finished_at']=now();record['build_logs']={p.name:sha(p) for p in [OUT/'build.jsonl',OUT/'build.stderr']};write_record()
 assert result.returncode==0,'isolated correctness build failed'
 artifacts=[json.loads(l) for l in (OUT/'build.jsonl').read_text().splitlines() if l.startswith('{')]
 harnesses=[a['executable'] for a in artifacts if a.get('reason')=='compiler-artifact' and a.get('target',{}).get('name')=='testsuite' and a.get('executable')]
 assert len(harnesses)==1
 harness=Path(harnesses[0]);cli=TARGET/'debug/cargo'
 assert cli.is_file() and harness.is_file()
 record['artifacts']={str(p):sha(p) for p in [cli,harness]};record['status']='testing';write_record()
 test_env=ENV.copy();test_env.pop('RUSTC',None);test_env.pop('RUSTDOC',None)
 test_env['CARGO_MANIFEST_DIR']=str(SOURCE)
 listing=subprocess.check_output([str(harness),'inheritable_workspace_fields::','--list'],cwd=SOURCE,env=test_env).decode();(OUT/'inheritance-list.txt').write_text(listing)
 names=[l[:-6] for l in listing.splitlines() if l.endswith(': test')]
 source_names=['inheritable_workspace_fields::'+m for m in re.findall(r'^fn (\w+)\(', (SOURCE/'tests/testsuite/inheritable_workspace_fields.rs').read_text(),re.M)]
 assert set(names)==set(source_names) and names
 run=['taskset','-c','0-7',str(harness),'inheritable_workspace_fields::','--nocapture','--test-threads=1']
 with (OUT/'inheritance.log').open('xb') as f:
  result=subprocess.run(run,cwd=SOURCE,env=test_env,stdout=f,stderr=subprocess.STDOUT,timeout=900)
 text=(OUT/'inheritance.log').read_text(errors='replace')
 counts=re.findall(r'test result: (?:ok|FAILED)\. (\d+) passed; (\d+) failed; (\d+) ignored;',text)
 executed=re.findall(r'^test (\S+) \.\.\.',text,re.M)
 record['checks'].append({'name':'inheritable_workspace_fields','command':run,'returncode':result.returncode,'selected_tests':names,'executed_tests':executed,'summary_counts':counts,'log_sha256':sha(OUT/'inheritance.log')});write_record()
 assert result.returncode==0 and counts==[(str(len(names)),'0','0')] and set(executed)==set(names)
 verify_source()
 assert {p:sha(p) for p in record['artifacts']}==record['artifacts']
 record['status']='passed';record['finished_at']=now();record['source_unchanged']=True;write_record()
 print(json.dumps({'status':record['status'],'tests':len(names),'cli':str(cli),'cli_sha256':sha(cli),'harness':str(harness),'harness_sha256':sha(harness)},indent=2),flush=True)
except BaseException as error:
 record.update(status='failed',error=repr(error),finished_at=now());write_record();raise
