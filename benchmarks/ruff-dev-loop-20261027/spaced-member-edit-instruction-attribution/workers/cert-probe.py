"""Capture Cargo's native process environment after OpenSSL certificate discovery."""
import json,os,subprocess,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent));import collect as x
w=x.w;m=w.m;O=x.O/'ssl-native-control';O.mkdir();(O/'bin').mkdir()
custom=O/'bin/cargo-report-local-ca';custom.write_text('#!/bin/sh\nprintf "%s\\n" "${SSL_CERT_FILE-}" "${SSL_CERT_DIR-}"\n');custom.chmod(0o755)
rows={}
for image in 'BC':
    i=O/image;i.mkdir();(i/'home').mkdir();(i/'cargo-home').mkdir()
    bind=json.loads((w.native/(image+'wasm-ty_wasm')/'binding.json').read_bytes());name=next(Path(k).name for k in bind['hashes'] if 'librustc_driver-' in k)
    loc=json.loads((w.source_k/'locations.json').read_bytes());donor=m.images/loc['common']
    env=dict(PATH=str(O/'bin')+':'+str(Path.home()/'.cargo/bin')+':/usr/local/bin:/usr/bin:/bin',HOME=str(i/'home'),CARGO_HOME=str(i/'cargo-home'),RUSTUP_HOME=str(w.native/('view-'+image+'wasm/rustup')),RUSTUP_TOOLCHAIN='ohm',RUSTUP_AUTO_INSTALL='0',LANG='C',CARGO_NET_OFFLINE='true',CARGO_TERM_COLOR='never')
    br=['bwrap','--ro-bind','/','/','--bind',str(i),str(i),'--dev','/dev','--proc','/proc','--tmpfs','/tmp','--ro-bind',str(donor),str(m.sdk),'--ro-bind',str(m.images/loc[image]['cargo']),str(m.sdk/'bin/cargo'),'--ro-bind',str(m.images/loc[image]['driver']),str(m.sdk/'lib'/name),'--chdir',str(i)]
    native=subprocess.run([*br,'--','cargo','+ohm','report-local-ca'],env=env,capture_output=True);assert not native.returncode,(native.returncode,native.stderr[-500:])
    vals=native.stdout.decode().splitlines();assert len(vals)==2 and all(vals)
    rows[image]=dict(zip(('SSL_CERT_FILE','SSL_CERT_DIR'),vals))
    assert Path(vals[0]).is_file() and all(Path(t).is_dir() for t in vals[1].split(':'))
    gr=x.O/'software-counters/callgrind'
    env.update(rows[image],VALGRIND_LIB=str(gr/'usr/libexec/valgrind'))
    br+=['--ro-bind',str(gr/'usr/lib/debug'),'/usr/lib/debug']
    test=subprocess.run([*br,'--',str(gr/'usr/bin/valgrind.bin'),'--tool=callgrind','--trace-children=no','--log-file='+str(i/'valgrind'),'--callgrind-out-file='+str(i/'startup-profile'),str(m.sdk/'bin/cargo'),'--version'],env=env,capture_output=True)
    (i/'version-stdout').write_bytes(test.stdout);(i/'version-stderr').write_bytes(test.stderr);x.emit(i/'return.json',{'returncode':test.returncode,'native':rows[image]})
    assert test.returncode==0 and test.stdout.startswith(b'cargo '),(test.returncode,test.stderr[-400:])
assert rows['B']==rows['C'];x.emit(O/'verified.json',rows)
