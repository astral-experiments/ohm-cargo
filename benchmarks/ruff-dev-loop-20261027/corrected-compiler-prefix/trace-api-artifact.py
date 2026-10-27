"""Run the exact before/after fixture with one logging-only release exemption and record real rustc outputs."""
from pathlib import Path
import gzip,hashlib,json,os,shutil,subprocess,sys
root=Path(__file__).resolve().parent;repo=Path('/home/dev-user/code/oss/ohm-rust-private-native-20261027');rel='tests/run-make/public-api-hash-artifact';tag,sha=sys.argv[1:];folder=root/'release-api-fixtures'/tag;folder.mkdir()
for p in (repo/rel).iterdir():
 if p.is_file():(folder/p.name).write_bytes(subprocess.check_output(['git','-C',repo,'show',sha+':'+rel+'/'+p.name]))
rm=folder/'rmake.rs';src=rm.read_text();exclude='    assert!(green_stderr.contains("copying preexisting metadata"), "{green_stderr}");';assert src.count(exclude)==1
rm.write_text(src.replace(exclude,'    // Shipping rustc statically disables the one DEBUG message; retain its work-product checks.'))
s=(root/'run-api-artifact-private.py').read_text()
a="shim=out/'rustc';shim.write_text('#!/bin/sh\\nexec '+str(rt/'bin/rustc')+' --sysroot '+str(rt)+' \"$@\"\\n');shim.chmod(0o755)"
start=s.index("shim=out/'rustc';");end=s.index('\ne=dict(env,RUSTC=',start)
b="""shim=out/'rustc';trace=out/'trace';trace.mkdir();shim.write_text('#!/usr/bin/python3\\n'+(d/'record-release-api-rustc.py').read_text().replace('__REAL_FRONT__',str(rt/'bin/rustc')).replace('__SYSROOT__',str(rt)).replace('__PRIVATE_RECORDS__',str(trace)));shim.chmod(0o755)"""
s=s[:start]+b+s[end:];runner=root/('trace-api-run-'+tag+'.py');runner.write_text(s)
p=subprocess.run(['python3',runner,'trace-'+tag,'2',root/'stage2-wire-v7a',folder]);sys.exit(p.returncode)
