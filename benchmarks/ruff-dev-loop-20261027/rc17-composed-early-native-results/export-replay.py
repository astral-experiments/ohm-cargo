"""Select portable inputs, ranges, raw hash receipts and replay outputs from the terminal H5 job."""
import collections
import gzip
import hashlib
import json
import mmap
from pathlib import Path
import struct
import sys

P=Path('/mnt/devbox-scratch/dev-user/ohm-combined-prs-20261028')
W=P/'ruff-evaluation-v2';CAN=W/'canonical';O=P/'wall-native-proofs';S=O/'width-v2'
def file_sha(f):
    with f.open('rb') as i:return hashlib.file_digest(i,'sha256').hexdigest()
def digest(x):return hashlib.sha256(json.dumps(x,separators=(',',':'),sort_keys=True).encode()).hexdigest()
def read(p):return json.loads(p.read_bytes())
def hx(f):return hashlib.sha256(str(f).encode()).hexdigest()
def relative(x):return str(Path(x).relative_to(CAN))
def ranges(f):
    with f.open('rb') as fd,mmap.mmap(fd.fileno(),0,access=mmap.ACCESS_READ) as b:
        assert b[:6]==b'\x7fELF\x02\x01';sh=struct.unpack_from('<Q',b,40)[0];step,count,ndx=struct.unpack_from('<HHH',b,58)
        assert step==64 and 0<ndx<count and sh+step*count<=len(b)
        sections=[struct.unpack_from('<IIQQQQIIQQ',b,sh+step*i)for i in range(count)];ss,sn=sections[ndx][4:6];wanted={}
        for i,s in enumerate(sections):
            pos=ss+s[0];end=b.find(b'\0',pos,ss+sn);assert ss<=pos<=end<ss+sn
            name=b[pos:end].decode()
            if name in ('.rodata','.note.gnu.build-id'):assert name not in wanted;wanted[name]=(i,s)
        i,ro=wanted['.rodata'];_,note=wanted['.note.gnu.build-id'];o=note[4]
        assert note[1]==7 and note[5]==48 and b[o:o+16]==struct.pack('<III',4,32,3)+b'GNU\0'
        spans=[('build-id',o+16,32),('rodata-sh-entsize',sh+step*i+56,8)]
        before=0;unchanged=[];values={};norm=hashlib.sha256()
        for name,off,length in sorted(spans,key=lambda s:s[1]):
            assert before<=off<off+length<=len(b)
            raw=memoryview(b)[before:off];norm.update(raw);unchanged.append([before,off,hashlib.sha256(raw).hexdigest()]);raw.release()
            norm.update(bytes(length));values[name]=[off,b[off:off+length].hex()];before=off+length
        raw=memoryview(b)[before:];norm.update(raw);unchanged.append([before,len(b),hashlib.sha256(raw).hexdigest()]);raw.release()
        return {'sha256':hashlib.sha256(b).hexdigest(),'bytes':len(b),'unchanged_ranges':unchanged,'fields':values,'normalized':norm.hexdigest()}
assert (O/'exit').read_text().strip()=='1' and (S/'exit').read_text().strip()=='0'
assert not list(O.glob('*/all-widths.json'))
failed=next(f for f in O.glob('*/rustc.stderr') if 'width-v2' not in f.parts)
assert b'Read-only file system' in failed.read_bytes()
known=read(S/'policy.json');end=read(S/'terminal.json');official=read(P/'sdk.json');stock=Path(official['sdk'])/'lib/rustlib/x86_64-unknown-linux-gnu/bin/wild-ld/ld.bfd'
assert file_sha(stock)==file_sha(S/'stock-wild')==official['tools']['wild'];admitted=read(O/'variants.json')
targets={};paths={};receipts={}
for name,term in end.items():
    cube=S/term['cube'];actual=read(cube/'all-widths.json');closure=read(cube/'private-inputs.json');argv=read(cube/'private-native-argv.json')
    assert actual['input_digest']==term['closure_sha256']==digest(closure)
    assert file_sha(cube/'private-inputs.json')==term['input_manifest'] and file_sha(cube/'private-native-argv.json')==term['args_manifest']
    assert set(actual['widths'])==set(map(str,range(1,17)))
    assert actual['hashed_before_and_after'] and actual['plain_and_diagnostic_equal_at_every_width']
    rows=[];unique={};args=set();inputs=set()
    for row in actual['all_16_receipts']:
        f=O/row['receipt'];r=read(f);artifact=O/row['elf']
        assert file_sha(f)==row['receipt_sha256']
        h=r['elf_sha256'];assert r['exit']==0 and h==r['with_depfile_sha256']==actual['widths'][str(r['threads'])]
        assert r['wild_sha256']==official['tools']['wild'] and r['target']==name and r['same_verified_inputs']
        assert file_sha(cube/(str(r['threads'])+'.d'))==r['depfile']
        if h not in unique:
            body=ranges(artifact);assert body['sha256']==h;unique[h]=body
        args.add(r['argv_except_width_and_output_sha256']);inputs.add(r['resolved_input_bytes_sha256'])
        rows.append({'width':r['threads'],'raw_sha256':h,'traced_dependency_file':r['depfile'],'status':r['exit'],'receipt_sha256':row['receipt_sha256']})
    assert len(inputs)==len(args)==1 and list(inputs)==[digest(closure)] and len(rows)==16
    assert len({digest([v['unchanged_ranges'],v['normalized']]) for v in unique.values()})==1
    chosen=set()
    if name in admitted:
        for v in admitted[name]['replays']:
            assert v in actual['all_16_receipts'];chosen.add(Path(v['elf']).name)
        assert chosen==set(unique) and len(chosen)>1
    else:
        assert len(unique)==1
    # Hash absolute tokens so reviewers can distinguish every path while keeping toolchain and registry paths local.
    portable=[]
    for path,item in sorted(closure.items()):
        a,b=Path(path),Path(item['resolved'])
        cls='cargo' if a.is_relative_to(CAN) else 'host' if a.is_relative_to('/usr') or a.is_relative_to('/lib') or a.is_relative_to('/lib64') else 'sdk' if b.is_relative_to(official['sdk']) else 'temporary'
        portable.append({'name':a.name,'path_sha256':hx(a),'resolved_path_sha256':hx(b),'kind':cls,'bytes':item['bytes'],'sha256':item['sha256']})
    pp=relative(name)
    targets[pp]={'identity':term['target'],'raw_by_phase':term['actual'],'widths':rows,'bodies':unique,'future_allowed':sorted(chosen),
                 'closure_sha256':term['closure_sha256'],'closure_bytes':term['bytes'],'closure_count':term['inputs'],
                 'portable_inputs_sha256':digest(portable),'stable_argv_sha256':list(args)[0],
                 'original_rustc_exec_sha256':term['source_rustc_exec'],'saved_rlink_sha256':term['rlink_sha256'],
                 'raw_private_argv_file':term['args_manifest'],'raw_private_input_file':term['input_manifest']}
    paths[pp]=portable
assert set(end)==set(known['targets']) and 1<=len(end)<=12 and len(admitted)==sum(bool(x['future_allowed']) for x in targets.values())
out={'release_wild':file_sha(stock),'failed_first_replay':{'exit':1,'successful_widths':0,'driver_sha256':file_sha(O/'replay.py'),'stderr_sha256':file_sha(failed),'reason':'The diagnostic shim entered its outer dispatcher before a plain Wild replay.'},
     'actual_native_rosters':known['receipts'],'corrected_driver_sha256':file_sha(S/'replay.py'),'width_order':known['widths'],
     'native_variant_manifest_sha256':file_sha(O/'variants.json'),'anticipation':{'observed_unstable':sorted(relative(x) for x in known['observed']),
         'earlier_ruff_target_controls':sorted(relative(x) for x in known['prior_history'])},'targets':targets,'input_files':paths,'timing_slots':0}
sys.stdout.buffer.write(gzip.compress(json.dumps(out,sort_keys=True,separators=(',',':')).encode(),mtime=0))
