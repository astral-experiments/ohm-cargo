#!/usr/bin/env python3
"""Compare current-option CLIs from real cold controls without running Cargo."""
import argparse
import collections
import hashlib
import importlib.util
import json
import mmap
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import time

here=Path(__file__).resolve().parent
s=importlib.util.spec_from_file_location('elf_parts',here/'elf_parts.py')
elf_parts=importlib.util.module_from_spec(s);s.loader.exec_module(elf_parts)
def read(p):return json.loads(p.read_bytes())
def sha(p):
    with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def decoder_capacity():
    mem=int(next(s.split()[1] for s in Path('/proc/meminfo').read_text().splitlines() if s.startswith('MemAvailable:')))*1024
    return mem>52*2**30 and all(shutil.disk_usage(p).free>140*2**30 for p in capacity_disks)

def run_one(r,key,path,section):
    subject=r/'elf'/key;assert sha(subject)==key
    args=[str(dum),'--debug-'+section,'--show-form',str(subject)]
    z=subprocess.Popen(args,stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.PIPE,bufsize=1024*1024)
    def maximum(*_):raise TimeoutError((key,section))
    signal.signal(signal.SIGALRM,maximum);signal.alarm(240)
    try:
        h=hashlib.sha256();raw=hashlib.sha256();blocks=[];b=hashlib.sha256();nl=nb=npath=0;start=time.monotonic()
        for line in z.stdout:
            raw.update(line);nb+=len(line)
            if nl==0:
                prefix=os.fsencode(str(subject))+b':\tfile format elf64-x86-64'
                assert line.rstrip(b'\n')==prefix,line[:200]
                line=b'SUBJECT.ELF:\tfile format elf64-x86-64\n'
            if path in line:
                npath+=line.count(path);line=line.replace(path,b'CANONICAL-JEMALLOC-COMP-DIR')
            h.update(line);b.update(line);nl+=1
            if nl%65536==0:
                blocks.append(b.hexdigest());b=hashlib.sha256();assert nb<2*2**30 and decoder_capacity()
        blocks.append(b.hexdigest());z.stdout.close();st=z.wait();err=z.stderr.read()
        assert st==0 and not err,(args,st,err[:800])
        return {'lines':nl,'original_bytes':nb,'path_replacements':npath,'raw_output_sha256':raw.hexdigest(),'canonical_output_sha256':h.hexdigest(),'each_65536_lines':blocks,'exit':st,'seconds':time.monotonic()-start}
    finally:
        signal.alarm(0)
        if z.poll() is None:z.kill();z.wait()

def prove_elf(root,rev,clean):
    module=elf_parts
    pairs=[clean[k] for k in 'PQ']
    digests=[v['CLI_ELF']['sha256'] for v in pairs]
    paths=[v['native_comp_dir'] for v in pairs]
    assert len(set(paths))==2 and len(paths[0])==len(paths[1])
    shape=re.compile(r'(.*/products/debug/build/workspaces/[0-9a-f]{16})/(v2-[0-9a-f]{16})/tikv-jemalloc-sys/([0-9a-f]{16})/out/build\Z')
    parsed=[shape.fullmatch(p) for p in paths]
    assert all(parsed) and parsed[0].groups()[:2]==parsed[1].groups()[:2] and parsed[0][3]!=parsed[1][3]
    files=[root/'elf'/v for v in digests]
    comparison=module.compare(*files)
    assert comparison['raw_sha256']==digests
    assert comparison['sizes'][0]==comparison['sizes'][1]
    assert len(comparison['all_PT_LOAD'])==4 and all(v['masked_a']==v['masked_b'] for v in comparison['all_PT_LOAD'])
    # A raw-equal ELF cannot contain both separately authenticated differing directories.
    # Require a literal path witness in both ELF files rather than weaken this admission.
    permitted={'.debug_info','.debug_macro','.debug_str','.note.gnu.build-id'}
    assert {'.debug_str','.note.gnu.build-id'}<=set(comparison['changed_sections'])<=permitted and not comparison['raw_equal'],(rev,comparison['changed_sections'].keys())
    tags=comparison['build_id_offset_size']
    assert tags[0]==tags[1] and tags[0][1]==32
    ranges=[tags[0]]
    for name,entry in comparison['changed_sections'].items():
        a,b=entry['a'],entry['b']
        assert all(a[k]==b[k] for k in ['type','offset','size','flags','entsize'])
        if name.startswith('.debug'):
            assert a['flags']&6==0
            ranges.append((a['offset'],a['size']))
        else:assert a['flags']&4==0
    n=0;summary=hashlib.sha256()
    with files[0].open('rb') as one,files[1].open('rb') as two:
        for start,length in sorted([*ranges,(comparison['sizes'][0],0)]):
            assert n<=start
            while n<start:
                size=min(1048576,start-n);x=one.read(size);y=two.read(size)
                assert len(x)==size and x==y,('raw bytes outside allowed fields',rev,n)
                summary.update(x);n+=size
            one.seek(length,1);two.seek(length,1);n+=length
        assert n==comparison['sizes'][0] and not one.read(1) and not two.read(1)
    groups=[]
    with files[0].open('rb') as one,files[1].open('rb') as two:
        for f,arm,key in [(one,'P','a'),(two,'Q','b')]:
            with mmap.mmap(f.fileno(),0,access=mmap.ACCESS_READ) as mm:
                sect,segments,note,_ro,raw,_size=module.image(mm)
                assert raw==clean[arm]['CLI_ELF']['sha256']
                for seg in segments:
                    if seg[0]==1 and seg[1]&1:
                        executable_start,executable_end=seg[2],seg[2]+seg[5]
                        assert all(start+size<=executable_start or start>=executable_end for start,size in ranges)
                ent=sect['.debug_str'];l=ent['offset'];z=ent['size']
                groups.append(collections.Counter(mm[l:l+z].split(b'\0')))
    assert groups[0]-groups[1]==collections.Counter({paths[0].encode():1}) and groups[1]-groups[0]==collections.Counter({paths[1].encode():1}),('literal jemalloc path',rev)
    assert sha(dum)=='07cf5eb367dcf51a8f462e046b08409fbe4a6fe60506fb0d4e5604db024873a1'
    data={arm:{} for arm in 'PQ'}
    for arm,k,path in zip('PQ',digests,paths):
        for section in ('info','macro'):
            data[arm][section]=run_one(root,k,path.encode(),section)
    for section in ('info','macro'):
        assert all(data['P'][section][k]==data['Q'][section][k] for k in ('lines','path_replacements','canonical_output_sha256','each_65536_lines'))
        if section=='info':assert data['P'][section]['path_replacements']>0
    return {'original_elf_sha256':digests,'independently_reported_compilation_directories':paths,
            'outside_allowed_bytes':comparison['sizes'][0]-sum(size for start,size in ranges),
            'outside_allowed_sha256':summary.hexdigest(),'ranges':ranges,'four_load_segments':comparison['all_PT_LOAD'],
            'changed_sections':comparison['changed_sections'],'complete_decodings':data,'dwarfdump_sha256':sha(dum)}

def main():
    global dum,capacity_disks
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('native_root',type=Path);ap.add_argument('output',type=Path)
    ap.add_argument('--decoder',type=Path,required=True)
    ap.add_argument('--capacity-disk',type=Path,action='append',required=True)
    args=ap.parse_args();root=args.native_root.resolve();dum=args.decoder.resolve();capacity_disks=args.capacity_disk
    assert len(capacity_disks)==2 and len({d.stat().st_dev for d in capacity_disks})==2
    assert decoder_capacity() and not args.output.exists()
    last=read(root/'independent-terminal.json');assert last['verified']==sha(root/'verified.json') and last['collection']==sha(root/'collection.json')
    check=read(root/'verified.json');assert check['same_flag_independent_raw_clean'] and check['same_physical_57']
    assert read(root/'collection.json')['source']=='08d49cba6aacb0cac27a96eea335ed1c7439f483'
    found={}
    for rev in 'AB':
        clean={}
        for label,arm in [('P','off'),('Q','on')]:
            mp=root/'runs'/(arm+'-storage')/('return-'+rev)
            second=root/'runs'/(arm+('-storage' if rev=='A' else '-clean-B'))/('empty-'+rev)
            row=read(mp/'result.json');cold=read(second/'result.json')
            assert all(cold[k]==row[k] for k in ('native_comp_dir','reader','CLI_ELF','observed','outcomes','graph_sha256','revision'))
            assert check['slots'][arm+'-storage']['return-'+rev]['cli']==row['CLI_ELF']
            for path in (mp,second):
                msgs=[json.loads(line) for line in (path/'cargo.stdout').read_bytes().splitlines()]
                nodes=[m for m in msgs if m.get('reason')=='build-script-executed' and 'tikv-jemalloc-sys' in m.get('package_id','')]
                assert len(nodes)==1
                node=nodes[0]
                assert node['out_dir']+'/build'==row['native_comp_dir'] and node['linked_libs']==['static=jemalloc_pic']
                assert node['linked_paths']==['native='+node['out_dir']+'/build/lib']
            linker,=[j for j in read(mp/'physical-native.json') if j['role']=='stock Wild']
            assert '-L'+row['native_comp_dir']+'/lib' in linker['argv']
            for archive in ('libtikv_jemalloc_sys-','libtikv_jemallocator-'):
                assert sum(archive in x and x.endswith('.rlib') for x in linker['argv'])==1
            clean[label]=row
        assert clean['P']['reader']==clean['Q']['reader'] and clean['P']['outcomes']==clean['Q']['outcomes']
        if clean['P']['CLI_ELF']==clean['Q']['CLI_ELF']:
            found[rev]={'runtime_terminal':sha(root/'independent-terminal.json'),'complete_raw_equal':clean['P']['CLI_ELF']}
        else:
            try:
                result=prove_elf(root,rev,clean)
            except BaseException as error:
                failure=args.output.with_name(args.output.stem+'-'+rev+'-failure.json')
                with failure.open('x') as out:
                    json.dump({'pass':False,'revision':rev,'current_off_on':[clean[k]['CLI_ELF'] for k in 'PQ'],
                        'directories':[clean[k]['native_comp_dir'] for k in 'PQ'],'exception':repr(error),
                        'native_terminal':sha(root/'independent-terminal.json')},out,sort_keys=True,indent=2);out.write('\n')
                raise
            found[rev]={'runtime_terminal':sha(root/'independent-terminal.json'),'full_reversible_comparison_passed':True,'result':result}
        with args.output.with_name(args.output.stem+'-'+rev+'-closed.json').open('x') as out:
            json.dump(found[rev],out,sort_keys=True,indent=2);out.write('\n')
    with args.output.open('x') as f:json.dump(found,f,sort_keys=True,indent=2);f.write('\n');f.flush();os.fsync(f.fileno())
    print(sha(args.output))
if __name__=='__main__':main()
