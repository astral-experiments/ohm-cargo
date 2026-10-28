"""Audit every ELF byte and decode all Rust and native DIE and macro records for the four affected products."""
from pathlib import Path
import fcntl,hashlib,json,mmap,os,re,socket,struct,subprocess,tempfile
P=Path('/mnt/devbox-scratch/dev-user/ohm-noquery-native-identity-20261028-h4')
BASE='/mnt/devbox-scratch/dev-user/ohm-empty-test-h4-20261027/native-target/debug/build/workspaces/38b7ca2992c44384/v2-'
NAMES={'A':'537fc98a7d00dcf2','B':'a60a9fe99525a185'}
ROLES=('ruff-main','ruff-test','ty-main','ty-test')
DIFF_DEBUG={'.debug_info','.debug_macro','.debug_str'}
sha=lambda x:hashlib.sha256(x).hexdigest()
strp=re.compile(rb'\(strp\) \(offset: (0x[0-9a-f]+|0)\): ')
def inspect(path,arm,record):
    scope=(BASE+NAMES[arm]).encode();common=(BASE+'@known-compiler@').encode();assert len(scope)==len(common)
    with path.open('rb') as f,mmap.mmap(f.fileno(),0,access=mmap.ACCESS_READ) as m:
        assert sha(memoryview(m))==record['sha256'] and len(m)==record['size'] and m[:6]==b'\x7fELF\x02\x01'
        sh=struct.unpack_from('<Q',m,40)[0];sz,count,index=struct.unpack_from('<HHH',m,58);assert sz==64
        headers=[struct.unpack_from('<IIQQQQIIQQ',m,sh+i*sz) for i in range(count)];off=headers[index][4];sects={};bytag={};regions=[]
        for i,h in enumerate(headers):
            start=off+h[0];name=m[start:m.find(b'\x00',start,off+headers[index][5])].decode();vals=dict(zip(('name_offset','type','flags','addr','offset','size','link','info','align','entsize'),h))
            assert name not in sects;v=dict(vals)
            if h[1]!=8:
                v['raw']=sha(memoryview(m)[h[4]:h[4]+h[5]])
            else:v['raw']=None
            sects[name]=v;bytag[name]=(i,h)
            if name in DIFF_DEBUG:assert h[2]&2==0 and h[1]==1;regions.append((h[4],h[5],name))
        assert set(bytag)>=DIFF_DEBUG|{'.rodata','.note.gnu.build-id','.text','.debug_line'}
        _,h=bytag['.note.gnu.build-id'];o=h[4];n,d,kind=struct.unpack_from('<III',m,o);assert n==4 and d==32 and kind==3 and m[o+12:o+16]==b'GNU\x00' and h[5]==48
        regions.append((o+16,d,'GNU build-ID descriptor'));wid,wh=bytag['.rodata'];assert wh[1]==1
        regions.append((sh+wid*sz+56,8,'actual .rodata sh_entsize cell'))
        wild=(wh[2],wh[9]);last=0;remain=hashlib.sha256()
        for start,n,name in sorted(regions):assert start>=last;remain.update(memoryview(m)[last:start]);last=start+n
        remain.update(memoryview(m)[last:]);_,h=bytag['.debug_str'];strings=m[h[4]:h[4]+h[5]];assert strings.endswith(b'\x00')
        canonical=strings.replace(scope,common);inventory=hashlib.sha256();entries=sorted(canonical.split(b'\x00'))
        for val in entries:inventory.update(struct.pack('<I',len(val)));inventory.update(val)
        specific=[v.decode('utf-8','strict') for v in strings.split(b'\x00') if scope in v]
        result={'section_table_offset':sh,'sections':sects,'allowlist_byte_ranges':sorted(regions),'all_other_bytes':remain.hexdigest(),'rodata_flags_and_entsize':list(wild),'raw_sha256':record['sha256'],'file_size':len(m),'debug_strings':{'entries':len(entries),'size':len(strings),'canonical_inventory':inventory.hexdigest(),'actual_namespace_spellings':specific}}
        del entries,canonical
        for part in ('macro','info'):
            with tempfile.TemporaryFile() as err:
                proc=subprocess.Popen(['readelf','--wide','--debug-dump='+part,str(path)],stdout=subprocess.PIPE,stderr=err,env={'PATH':'/usr/bin:/bin','LC_ALL':'C'})
                normalized=hashlib.sha256();raw=hashlib.sha256();lines=refs=rewrites=0;uses=[]
                for line in proc.stdout:
                    raw.update(line);lines+=1
                    if part=='info' and b'(strp) (offset: ' in line:
                        ref=strp.search(line);assert ref,line[:200];address=int(ref[1],0);end=strings.find(b'\x00',address);assert 0<=address<len(strings) and end>=address
                        literal=line[ref.end():].rstrip(b'\n');stored=strings[address:end]
                        # GNU may render escaped control bytes differently. Every exact raw reference target is retained separately regardless of its presentation.
                        normalized.update(b'\x00strp\x00');checked=stored.replace(scope,common);normalized.update(struct.pack('<I',len(checked)));normalized.update(checked)
                        line=line[:ref.start(1)]+b'@str-offset@'+line[ref.end(1):];refs+=1
                    if scope in line:
                        uses.append(line.decode('utf-8','backslashreplace').strip());rewrites+=line.count(scope);line=line.replace(scope,common)
                    normalized.update(line)
                assert proc.wait()==0;err.seek(0);warnings=err.read();result[part]={'lines':lines,'strp':refs,'namespace_count':rewrites,'namespace_attributes':uses,'raw':raw.hexdigest(),'decoded':normalized.hexdigest(),'stderr':sha(warnings),'stderr_len':len(warnings)}
        return result
def analyze(left,right):
    keys=left['sections'].keys();assert keys==right['sections'].keys();different=[n for n in keys if left['sections'][n]!=right['sections'][n]]
    payload=[n for n in keys if left['sections'][n]['raw']!=right['sections'][n]['raw']]
    layout=[]
    for n in keys:
        a,b=left['sections'][n],right['sections'][n];layout +=[(n,k,a[k],b[k]) for k in a if k!='raw' and a[k]!=b[k]]
    a,left_width=left['rodata_flags_and_entsize'];b,right_width=right['rodata_flags_and_entsize']
    width_ok=left_width==right_width or (min(left_width,right_width)==0 and max(left_width,right_width) in {1,2,4,8,16,32,64,128,256} and a==b and a&0x12==0x12 and not a&0x5)
    scope=[]
    for arm,res in zip('AB',(left,right)):
        names=res['debug_strings']['actual_namespace_spellings'];scope.append([s.replace(BASE+NAMES[arm],BASE+'@known-compiler@') for s in names])
    info_equal=all((left[k]['decoded'],left[k]['lines'],left[k]['strp'],left[k]['namespace_count'],left[k]['stderr_len'])==(right[k]['decoded'],right[k]['lines'],right[k]['strp'],right[k]['namespace_count'],0) and left[k]['lines']>10000 for k in ('info','macro'))
    true_names=scope[0]==scope[1] and len(scope[0])==1 and ('jemalloc' in scope[0][0]) and all(len(res['info']['namespace_attributes'])>=1 and all('DW_AT_comp_dir' in l for l in res['info']['namespace_attributes']) for res in (left,right))
    native_ok=left['all_other_bytes']==right['all_other_bytes'] and left['file_size']==right['file_size'] and left['allowlist_byte_ranges']==right['allowlist_byte_ranges'] and all(p in DIFF_DEBUG|{'.note.gnu.build-id'} for p in payload) and all(n=='.rodata' and k=='entsize' for n,k,_,_ in layout) and width_ok
    return {'different_named_sections':different,'payload_differences':payload,'section_metadata_differences':layout,'all_code_data_and_unclaimed_ELF_bytes_identical':native_ok,'exact_decoded_debug':info_equal and left['debug_strings']['canonical_inventory']==right['debug_strings']['canonical_inventory'] and true_names,'common_jemalloc_source':scope[0] if true_names else None,'debug_text_equivalent':info_equal,'namespace_evidence_pass':true_names}
def main():
    assert socket.gethostname()=='charlie-ohm-loader-perf-1024';os.sched_setaffinity(0,{12,13,14,15});rec=json.loads((P/'selected.json').read_bytes());assert (P/'transfer.json').is_file()
    with (P/'offline-decode.lock').open('xb') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        result={'gnu_readelf_sha':sha(Path('/usr/bin/readelf').read_bytes()),'gnu_readelf_version':subprocess.check_output(['readelf','--version'],text=True).splitlines()[0],'products':{},'differential':{}}
        for role in ROLES:
            for arm in 'AB':
                n=arm+'-'+role;result['products'][n]=inspect(P/n,arm,rec[n]);(P/(n+'.decoded.json')).write_text(json.dumps(result['products'][n],sort_keys=True,indent=2)+'\n')
            fields=analyze(result['products']['A-'+role],result['products']['B-'+role]);result['differential'][role]=fields;print(role,fields,flush=True)
        (P/'results.json').write_text(json.dumps(result,sort_keys=True,indent=2)+'\n')
if __name__=='__main__':main()
