"""Local synthetic fail-closed checks. This program never runs Cargo or starts any wall slot."""
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import tempfile

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
import guards as g
from runner import readonly_seed_inodes,top_diagnostics


def rejected(f):
    try:
        f()
    except (AssertionError,ValueError):
        return True
    raise RuntimeError('Expected rejection')


def test():
    target='/state/e2e-123'
    products={'e2e':[target],'ty_server':{'file':'/state/libty_server-0123.rlib','fresh':True}}
    e={'kind':'full','target':'e2e','exit':0,'argv':['rustc','--test','crates/ty_server/tests/e2e/main.rs','--extern','ty_server=/state/libty_server-0123.rlib']}
    w={'kind':'wild','target':target,'exit':0,'argv':['ld.bfd','-o',target]}
    ron={'kind':'full','target':'ron','exit':0,'argv':['rustc']}
    unrelated={'kind':'wild','target':'/state/other','exit':0,'argv':['ld.bfd']}
    first=[ron,unrelated,e,w];repeat=[ron,unrelated]
    assert g.native_cut(first+[e,w],repeat,products,'B')==g.native_cut(first,repeat,products,'C')
    assert rejected(lambda:g.native_cut(first,repeat,products,'B'))
    assert rejected(lambda:g.native_cut(first+[e,w],repeat,products,'C'))
    assert rejected(lambda:g.native_cut(first,[],products,'C'))
    assert rejected(lambda:g.native_cut([*first,dict(ron,exit=1)],repeat,products,'C'))
    assert rejected(lambda:g.native_cut([ron,unrelated,dict(e,argv=e['argv'][:-1]),w],repeat,products,'C'))
    assert g.native_cut(first+[unrelated],repeat,products,'C')!=g.native_cut(first+[e,w],repeat,products,'B')
    x={str(i):str(i).zfill(64) for i in range(110)}
    ok={k:[v] for k,v in x.items()};g.check_raw(x,ok)
    assert rejected(lambda:g.check_raw(dict(x,**{'0':'f'*64}),ok))
    assert rejected(lambda:g.check_raw({k:v for k,v in x.items() if k!='0'},ok))
    r={'diagnostics':[['unit',{'rendered':'warning: retained message\n  --> input.rs\n','level':'warning'}]]}
    assert top_diagnostics('warning: retained message\nwarning: `unit` (lib) generated 1 warning\n',r)=={'warning: retained message':1}
    assert rejected(lambda:top_diagnostics('warning: another message\n',r))
    assert rejected(lambda:top_diagnostics('Finished\n',r))
    with tempfile.TemporaryDirectory() as t:
        tmp=Path(t);seed=tmp/'seed';copy=tmp/'copy';seed.mkdir();(seed/'file').write_bytes(bytes(range(255)))
        os.link(seed/'file',seed/'alias');(seed/'relative').symlink_to('file')
        subprocess.run(['cp','-a','--reflink=never',seed,copy],check=True)
        assert g.tree(seed)==g.tree(copy);readonly_seed_inodes(seed,copy)
        st=(copy/'file').stat();(copy/'file').write_bytes(bytes(reversed(range(255))))
        os.utime(copy/'file',ns=(st.st_atime_ns,st.st_mtime_ns))
        assert g.tree(seed)!=g.tree(copy)
        (copy/'alias').unlink();os.link(seed/'file',copy/'alias')
        assert rejected(lambda:readonly_seed_inodes(seed,copy))
        elf=tmp/'ordinary';subprocess.run(['cc','-xc','-','-o',elf,'-Wl,--build-id=0x'+'12'*32],input=b'int main(void){return 0;}\n',check=True)
        raw=bytearray(elf.read_bytes());sh=struct.unpack_from('<Q',raw,40)[0];step,num,si=struct.unpack_from('<HHH',raw,58)
        rows=[struct.unpack_from('<IIQQQQIIQQ',raw,sh+i*step) for i in range(num)]
        names=rows[si][4];sections={raw[names+r[0]:raw.index(0,names+r[0])].decode():(i,r) for i,r in enumerate(rows)}
        stock=g.fingerprint(elf);i,r=sections['.rodata'];note=sections['.note.gnu.build-id'][1]
        raw[note[4]+16]^=1;struct.pack_into('<Q',raw,sh+i*step+56,0 if r[9] else 8);elf.write_bytes(raw)
        known=g.fingerprint(elf);assert stock['normalized']==known['normalized'] and stock['build_id']!=known['build_id'] and stock['rodata_entsize']!=known['rodata_entsize']
        raw[sections['.text'][1][4]]^=1;elf.write_bytes(raw);assert g.fingerprint(elf)['normalized']!=stock['normalized']
    return dict(correct_native_job_reduction=True,same_projection_elsewhere=True,no_decrease_rejected=True,
                changed_other_target_rejected=True,missing_observer_rejected=True,wrong_extern_rejected=True,
                failed_rustc_rejected=True,strict_110=True,unknown_hash_rejected=True,missing_path_rejected=True,
                full_copy_digest_and_hardlinks=True,same_size_backdated_bytes_rejected=True,cross_state_hardlinks_rejected=True,
                ordinary_warning_gates=True,wild_fields_only=True,modified_text_rejected=True,actual_workstation_cargo_invocations=0)


if __name__=='__main__':
    print(json.dumps(test(),sort_keys=True,indent=2))
