"""Isolated direct native CLI and ordinary Cargo checks of raw Unix linker filenames."""
import ast,hashlib,json,os,re,shutil,subprocess,sys,tempfile
from pathlib import Path
H=lambda b:hashlib.sha256(b).hexdigest()
def digest(p):
    with p.open('rb')as f:return hashlib.file_digest(f,'sha256').hexdigest()
def norm(b,root):
    return b.decode('utf-8','backslashreplace').replace(str(root),'<work>')
def save(f,v):f.write_text(json.dumps(v,ensure_ascii=True,sort_keys=True,indent=2)+'\n')
def asm(p,src):
    r=subprocess.run(['/usr/bin/as','--64','-o',os.fsencode(p)],input=src.encode(),capture_output=True);assert not r.returncode,r.stderr
def traces(data,root):
    out=[]
    for s in data.decode('utf8','replace').splitlines():
        if 'execve(' not in s or '= 0' not in s:continue
        pre,tail=s.split('execve(',1);p=tail.split('", [',1)[0].lstrip('"');k=Path(p).name
        if k in ('rustc','cc','collect2','ld.bfd','rust-lld'):out.append({'kind':k,'raw_ff_octal':bool(re.search(r'(?<!\\)\\377',s)),'raw_fd_octal':bool(re.search(r'(?<!\\)\\375',s)),'argv_line_sha256':H(s.encode()),'exe':p if k in ('ld.bfd','rust-lld')else k})
    return out
def run(root,sdkname,sdk,only_direct=False):
    state=root/sdkname;state.mkdir();sdk=sdk.resolve()
    linker_dir=sdk/'lib/rustlib/x86_64-unknown-linux-gnu/bin'; wild=linker_dir/'wild-ld/ld.bfd';lld=linker_dir/'rust-lld'
    info={k:digest(f)for k,f in {'cargo':sdk/'bin/cargo','rustc':sdk/'bin/rustc','rust-lld':lld,'wild':wild}.items()}
    info['rustc_version']=subprocess.check_output([sdk/'bin/rustc','-vV']).decode()
    native=state/'obj';native.mkdir()
    P=lambda raw:native/os.fsdecode(raw)
    objects={'ascii':P(b'val.o'),'raw':P(b'val-\xff.o'),'decoy':P('val-�.o'.encode())}
    for k,ob in objects.items():asm(ob,'.text\n.globl foreign_value\n.type foreign_value,@function\nforeign_value: mov $'+('99' if k=='decoy' else '41')+', %eax; ret\n.section .note.GNU-stack,"",@progbits\n')
    assert digest(objects['raw'])==digest(objects['ascii'])!=digest(objects['decoy'])
    entry=native/'entry.o';asm(entry,'.text\n.globl _start\n_start: call foreign_value; mov %eax,%edi;mov $60,%eax;syscall\n.section .note.GNU-stack,"",@progbits\n')
    rows=[];response=native/'objects.rsp';rawresponse=P(b'objects-\xfd.rsp')
    rawresponse.write_bytes(os.fsencode(objects['ascii'])+b'\n')
    directcases=['ascii','raw-positional','raw-output','raw-response-name','ascii-response','raw-response-body','raw-argv0']
    for toolname,ex in [('wild',wild),('rust-lld',lld)]:
        first=None
        for case in directcases:
            output=P(b'out-\xff-'+toolname.encode()) if case=='raw-output' else native/(toolname+'-'+case)
            rp=objects['raw'] if case in ('raw-positional','raw-response-body')else objects['ascii']
            argv0=b'ld-\xff' if case=='raw-argv0' else os.fsencode(ex)
            response.write_bytes(os.fsencode(rp)+b'\n')
            token=(b'@'+os.fsencode(rawresponse) if case=='raw-response-name'else b'@'+os.fsencode(response) if case.endswith('-response') or case=='raw-response-body'else os.fsencode(rp))
            cmd=[argv0,*([b'-flavor',b'gnu']if toolname=='rust-lld'else[]),b'-m',b'elf_x86_64',b'--build-id',b'-o',os.fsencode(output),os.fsencode(entry),token]
            q=subprocess.run(cmd,executable=os.fsencode(ex),cwd=native,capture_output=True)
            value=subprocess.run([output],capture_output=True).returncode if q.returncode==0 and output.exists()else None
            sig=digest(output) if q.returncode==0 and output.exists()else None
            if case=='ascii':first=sig
            rows.append(dict(level='direct',case=case,tool=toolname,rc=q.returncode,program=value,panic=b'panicked at' in q.stderr,stderr=norm(q.stderr,root),elf=sig,same_as_ascii=(sig==first if sig else None)))
    if not only_direct:
        rup=state/'rustup';(rup/'toolchains').mkdir(parents=True);(rup/'toolchains/ohm').symlink_to(sdk)
        for name in ('home','cargo','shared','tmp'): (state/name).mkdir()
        proj=state/'work';proj.mkdir()
        def crate(at):
            (at/'src').mkdir()
            (at/'Cargo.toml').write_text('[package]\nname="raw_native_name"\nversion="0.0.0"\nedition="2021"\n')
            (at/'src/main.rs').write_text('unsafe extern "C" { fn foreign_value() -> i32; }\nfn main() { println!("{}", unsafe { foreign_value() }); }\n')
            (at/'build.rs').write_text('fn main() { println!("cargo:rerun-if-changed={}",std::env::var("PROBE_RSP").unwrap()); println!("cargo:rustc-link-arg=@{}",std::env::var("PROBE_RSP").unwrap()); }\n')
        crate(proj); odd=state/os.fsdecode(b'project-\xff');odd.mkdir();crate(odd)
        def cargo(case,project,target,raw):
            target.mkdir();response.write_bytes(os.fsencode(objects['raw'] if raw else objects['ascii'])+b'\n')
            env=dict(PATH=str(Path.home()/'.cargo/bin')+':/usr/local/bin:/usr/bin:/bin',HOME=str(state/'home'),USER='dev-user',RUSTUP_HOME=str(rup),RUSTUP_TOOLCHAIN='ohm',RUSTUP_AUTO_INSTALL='0',CARGO_NET_OFFLINE='true',CARGO_HOME=str(state/'cargo'),CARGO_TARGET_DIR=str(target),CARGO_BUILD_BUILD_DIR=str(state/'shared'),TMPDIR=str(state/'tmp'),LANG='C.UTF-8',LC_ALL='C.UTF-8',PROBE_RSP=str(response),CARGO_TERM_COLOR='never')
            cmd=['cargo','+ohm','build','--offline','-j2']; d=state/('cargo-'+case);d.mkdir();trace=d/'exec.log';q=subprocess.run(['strace','-q','-f','-xx','-s','8192','-e','trace=execve','-o',str(trace),*cmd],cwd=project,capture_output=True,env=env)
            # strace -xx emitted literal bytes; decode each quoted sequence to an ASCII/escaped wire view.
            raw_txt=trace.read_bytes(); display=re.sub(rb'(?:\\x[0-9a-fA-F]{2})+',lambda m:b''.join(bytes([x]) if 32<=x<127 else ('\\%03o'%x).encode() for x in bytes.fromhex(m.group().replace(b'\\x',b'').decode())),raw_txt)
            (d/'stdout').write_bytes(q.stdout);(d/'stderr').write_bytes(q.stderr)
            actual=target/'debug/raw_native_name';val=subprocess.run([actual],capture_output=True).stdout.decode().strip() if q.returncode==0 and actual.exists() else None
            record=dict(level='cargo',case=case,tool='cargo +ohm build',rc=q.returncode,program=val,panic=b'panicked at'in q.stderr,diagnostic_tail=norm(q.stderr[-2600:],root),trace_file_sha256=H(raw_txt),trace=traces(display,root))
            rows.append(record)
        for case,project,target,raw in [('ascii',proj,state/'t-ascii',False),('gcc-rsp-raw',proj,state/'t-raw',True),('nonunicode-project',odd,state/'t-cwd',False),('nonunicode-target',proj,state/os.fsdecode(b't-\xff'),False)]:cargo(case,project,target,raw)
    report=dict(sdk=info,input_link_objects={'ascii':digest(objects['ascii']),'raw':digest(objects['raw']),'decoy':digest(objects['decoy']),'entry':digest(entry)},rows=rows)
    save(state/'report.json',report);return report
def main():
    root=Path(sys.argv[1]).resolve();root.mkdir();allr={}
    for s in sys.argv[2:]:
        tag,st=s.split('=',1);allr[tag]=run(root,tag,Path(st))
        print(tag,[(v['case'],v['tool'],v['rc'],v['program'])for v in allr[tag]['rows']],flush=True)
    save(root/'complete.json',allr)
if __name__=='__main__':main()
