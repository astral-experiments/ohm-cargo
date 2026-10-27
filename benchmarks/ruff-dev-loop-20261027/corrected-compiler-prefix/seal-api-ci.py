from pathlib import Path
import difflib,gzip,hashlib,json,shutil,subprocess
d=Path(__file__).resolve().parent;e=d/'release-api-ci-evidence';e.mkdir(exist_ok=True);repo=Path('/home/dev-user/code/oss/ohm-rust-private-native-20261027');head='378b7a8202a270aac0a47610e99527125ec432ca';old='66815c41574c8c597fa06af78a38c4c40ca30a84';rel='tests/run-make/public-api-hash-artifact/rmake.rs';driver=d/'stage2-wire-v7a/librustc_driver-774a793a844d5500.so';sha=lambda p:hashlib.file_digest(p.open('rb'),'sha256').hexdigest();assert sha(driver)=='3e4b168966e111b52ad1a942d364ec1335cf1cfa994f4208b0909ca215b589d2';assert subprocess.check_output(['git','-C',repo,'rev-parse',old+':compiler',head+':compiler']).decode().split()==['9e52c043880793c40fedf3eb137a231479d9adba']*2
def cp(p,n):shutil.copyfile(p,e/n)
records={}
summary={'before_fixture':old,'after_fixture':head,'compiler_tree':'9e52c043880793c40fedf3eb137a231479d9adba','driver_sha256':sha(driver),'ci_test':rel}
for group,revision in [('before',old),('after',head)]:
 tag=group+'-sealed';root=d/'rmake'/('wire-trace-'+tag);trace=[json.loads(f.read_bytes()) for f in sorted((root/'trace').glob('*.json'))];assert len(trace)==(21 if group=='before' else 76);records[group]=trace
 version=subprocess.check_output(['git','-C',repo,'show',revision+':'+rel]).decode().splitlines(keepends=True);private=(d/'release-api-fixtures'/tag/'rmake.rs').read_text().splitlines(keepends=True);diff=''.join(difflib.unified_diff(version,private,fromfile=revision+'/'+rel,tofile='local-release-probe/'+rel));assert diff.count('\n@@')==1 and 'copying preexisting metadata' in diff;(e/(group+'-logging-exemption.patch')).write_text(diff)
 green=trace[1]['links'];assert green['original-metadata.rmeta']==green['liblib.rmeta'];summary[group]={'invocations':len(trace),'work_product_matches_original_inode_and_length':True}
 cp(root/'stderr',group+'-run-make.stderr')
oldrows=records['before'];assert oldrows[17]['metadata_hash']==oldrows[19]['metadata_hash'] and oldrows[20]['metadata_hash']!=oldrows[17]['metadata_hash'];assert 'rmake.rs:309:5' in (e/'before-run-make.stderr').read_text() and 'panicked' not in (e/'after-run-make.stderr').read_text()
j=records['after'];summary['after']['prefix_and_hash']={}
for name,idx in {'tracked-native':[19,21,22,24],'private-method-native':[26,28,29,31],'exported-macro-native':[50,53,55,57]}.items():
 r=[j[i] for i in idx];h=[v['metadata_hash'][0] for v in r];p=[v['reused_prefix'] for v in r];assert h[0]==h[1] and h[2]==h[3] and h[0]!=h[2] and p==[False,True,False,True];assert all(v['prefix_messages'] for v in (r[1],r[3]));summary['after']['prefix_and_hash'][name]={'rustc_invocations':idx,'public_hashes':h,'actual_prefix_reuse_info':p}
 checks=[j[i] for i in (17,18)];assert checks[0]['metadata_hash']==checks[1]['metadata_hash'] and not any(i['reused_prefix'] for i in checks);summary['after']['prefix_and_hash']['tracked-metadata-only']={'rustc_invocations':[17,18],'public_hashes':checks[0]['metadata_hash']*2,'actual_prefix_reuse_info':[False,False]}
cols=[]
for index in (27,30,32):
 mm=[json.loads(l) for l in j[index]['stderr'].splitlines() if l.startswith('{')];di=next(m for m in mm if m.get('code',{}).get('code')=='E0624');sp=[*di['spans'],*(s for x in di['children'] for s in x['spans'])];col=next(s['column_start'] for s in sp if s['label']=='private method defined here');cols.append(col)
assert cols[1]==cols[0]+256 and cols[2]==cols[1];summary['after']['real_downstream_private_method_columns']=cols
(e/'rustc-calls.json.gz').write_bytes(gzip.compress(json.dumps(records,separators=(',',':')).encode(),mtime=0));(e/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
for f in ('trace-api-artifact.py','run-api-artifact-private.py','record-release-api-rustc.py','seal-api-ci.py'):cp(d/f,f)
cp(d/'rmake/wire-api-artifact-original-corrected/stderr','unmodified-release-debug-limit.stderr');cp(d/'rmake/wire-api-artifact-original-stage1/stderr','unmodified-stage1-debug-limit.stderr')
(e/'README.md').write_text('''# Linux release replay of the CI artifact fixture

The same PGO/BOLT compiler ran the fixture from PR head `66815c41574c` and its updated head `378b7a8202a2`. Both revisions have the same compiler tree. The shipping Linux build has a static log ceiling of INFO. The unmodified fixture exits at the assertion requiring the DEBUG message for copying a green metadata work product. The local copy removes that single log-text assertion on both arms. The exact diffs are included. Each traced run independently verifies that the green output has the same filesystem inode and length as the original retained metadata.

The earlier fixture then reproduces the macOS CI failure at line 309. The corrected fixture passes all remaining checks against the release compiler. The metadata-only tracked declaration still collides when moved by 256 columns and the compiler re-encodes its metadata prefix. The three native cases change API hashes. Only the two private-only follow-up edits in each native sequence emit the INFO-level encoder message confirming a reused prefix. The emitted downstream private-method diagnostic moves from column 19 to 275 and stays there.

The compressed trace contains the actual compiler argv, inputs, standard output, standard error, exit status and metadata hashes for all 21 before and 76 after rustc calls. The unmodified CI uses a debug-logging compiler and retains the original green-copy assertion.
''')
m={p.name:sha(p) for p in sorted(e.iterdir()) if p.name!='SHA256.json'};(e/'SHA256.json').write_text(json.dumps(m,indent=2)+'\n');print(len(m),sha(e/'SHA256.json'),cols)
