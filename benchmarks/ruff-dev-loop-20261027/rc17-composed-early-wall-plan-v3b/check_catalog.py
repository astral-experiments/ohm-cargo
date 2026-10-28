"""Use generated ELF files and the public, unscored 297-link census to test the native gate."""
import copy
import gzip
import hashlib
import json
from pathlib import Path
import struct
import sys
import tempfile

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
from catalog import catalog_view, check_ci, expected_kind, sha
p=json.loads((HERE/'plan.json').read_bytes())
h=json.loads(gzip.decompress((HERE/'historical-links.json.gz').read_bytes()))['phases']


def elf(content,entsize):
    names=b'\0.shstrtab\0.rodata\0.note.gnu.build-id\0'
    chunks=[names,content,b'']
    off=64;offsets=[]
    for blob in chunks:
        offsets.append(off);off+=len(blob)
    chunks[-1]=struct.pack('<III',4,32,3)+b'GNU\0'+hashlib.sha256(content+bytes([entsize])).digest()
    off+=len(chunks[-1]);header=bytearray(64)
    header[:6]=b'\x7fELF\x02\x01';struct.pack_into('<H',header,18,62)
    struct.pack_into('<Q',header,40,off);struct.pack_into('<HHH',header,58,64,4,1)
    sections=[bytes(64)]
    for name,kind,start,chunk,size in zip((b'.shstrtab',b'.rodata',b'.note.gnu.build-id'),(3,1,7),offsets,chunks,(0,entsize,0)):
        sections.append(struct.pack('<IIQQQQIIQQ',names.index(name),kind,0,0,start,len(chunk),0,0,1,size))
    return bytes(header)+b''.join(chunks+sections)


def reject(fn):
    try:fn()
    except (AssertionError,KeyError,ValueError):return
    raise RuntimeError('Unadmitted fixture passed')


def fixture(root):
    witness=root/'receipt.json';witness.write_bytes(b'{"synthetic":true}\n')
    ref={'file':witness.name,'sha256':sha(witness)}
    view={'schema':1,'wild_sha256':p['sdk']['tools']['wild'],'wild_source':p['catalog_scope']['public_wild_source'],'cpu':p['cpu'],'jobs':8,
          'widths':list(range(1,17)),'native_ref':p['catalog_scope']['native_reference'],'terminal':ref,'independent_verification':ref,
          'historical':copy.deepcopy(h),'fresh':{},'targets':{}}
    names=sorted({j['target'] for js in h.values() for j in js});prior={};emitted={};bad={}
    for name in names:
        content=name.encode()
        bodies={};raw=[]
        for ent in (0,8):
            data=elf(content,ent);key=hashlib.sha256(data).hexdigest();(root/key).write_bytes(data);bodies[key]=key;raw.append(key)
        prior[name]=[raw[0]];emitted[name]=raw[0]
        if Path(name).name in p['stopped_v2']['unadmitted']:bad[name]=raw[1]
        widths=[{'width':w,'plain_sha256':raw[w%2],'depfile_sha256':raw[w%2],'plain_exit':0,'depfile_exit':0} for w in view['widths']]
        recipe={'inputs_sha256':hashlib.sha256(content).hexdigest(),'stable_argv_sha256':ref['sha256'],'bodies':bodies,'widths':widths}
        view['targets'][name]={'evidence':ref,'recipes':{'family':recipe}}
    for i in range(60):prior['frozen/'+str(i)]=[hashlib.sha256(str(i).encode()).hexdigest()]
    for phase,rows in h.items():
        view['fresh'][phase]=[{'target':j['target'],'kind':expected_kind(phase,j['target']),'occurrence':str(i),'exit':0,'wild_sha256':view['wild_sha256'],
            'raw_sha256':emitted[j['target']],'recipe':'family','exec_sha256':j['exec_sha256'],'argv_sha256':j['argv_sha256'],'capture':ref} for i,j in enumerate(rows)]
    outputs={ph:{j['target']:emitted[j['target']] for j in rows} for ph,rows in h.items()}
    return view,prior,outputs,bad


def main():
    ci=json.loads((HERE/'ci-exact-heads.json').read_bytes());check_ci(p,ci)
    def reject_ci(update):
        c=copy.deepcopy(ci);update(c);reject(lambda:check_ci(p,c))
    reject_ci(lambda c:c[0].update(head=p['source']['guard']))
    reject_ci(lambda c:c[1]['checks'][0].update(conclusion='FAILURE'))
    reject_ci(lambda c:c[0]['checks'].pop(0))
    with tempfile.TemporaryDirectory() as td:
        root=Path(td);v,prior,products,bad=fixture(root)
        def run(v):return catalog_view(root,v,h,p,prior,products,bad)
        results=run(v);assert len(results)==110 and sum(len(x)==1 for x in results.values())==60
        first=next(iter(v['targets']));rep=v['fresh']['repeat-observer'][0]['target']
        def test(update):
            view=copy.deepcopy(v);update(view);reject(lambda:run(view))
        test(lambda v:v['targets'].pop(first))
        test(lambda v:v['targets'].update({'frozen/1':v['targets'][first]}))
        test(lambda v:v['historical']['selected-observer'][0].update(exec_sha256='e'*64))
        test(lambda v:v['fresh']['selected-observer'].pop(next(i for i,a in enumerate(v['fresh']['selected-observer']) if a['kind']=='full' and Path(a['target']).name.startswith('e2e-'))))
        test(lambda v:v['fresh']['repeat-observer'][0].update(kind='full'))
        test(lambda v:v['fresh']['repeat-observer'][0].update(exit=1))
        test(lambda v:v['fresh']['repeat-observer'][0].update(wild_sha256='b'*64))
        test(lambda v:v['targets'][first]['recipes']['family']['widths'].pop(0))
        test(lambda v:v['targets'][first]['recipes']['family']['widths'][0].update(depfile_sha256='e'*64))
        test(lambda v:v['targets'][first]['recipes']['family']['widths'][0].update(plain_exit=1))
        test(lambda v:v['fresh']['repeat-observer'][0].update(raw_sha256='c'*64))
        test(lambda v:v['targets'][first].update(evidence={'file':'../outside','sha256':'a'*64}))
        assert len(bad)==2
        def suppress_previous_failure(v):
            t=next(iter(bad));r=v['targets'][t]['recipes']['family'];known=prior[t][0]
            for w in r['widths']:w.update(plain_sha256=known,depfile_sha256=known)
            r['bodies']={known:known}
        test(suppress_previous_failure)
        def substitute_payload(v):
            r=v['targets'][rep]['recipes']['family'];old=next(h for h in r['bodies'] if h!=prior[rep][0]);contents=elf(b'wrong machine bytes',8)
            new=hashlib.sha256(contents).hexdigest();(root/new).write_bytes(contents);r['bodies'].pop(old);r['bodies'][new]=new
            for w in r['widths']:
                if w['plain_sha256']==old:w.update(plain_sha256=new,depfile_sha256=new)
        test(substitute_payload)
    return dict(real_published_historical_occurrences=297,synthetic_native_groups=50,synthetic_full_widths=16,singleton_unlinked=60,
                new_default_outputs_require_same_exact_input_family=True,skipped_or_failed_width_rejected=True,
                lost_duplicate_or_native_evidence_rejected=True,old_failure_absent_rejected=True,
                changed_ordinary_elf_content_rejected=True,other_uninvolved_product_rejected=True,old_pr_head_rejected=True,
                eight_applicable_checks_per_current_head=True,real_toolchain_or_linker_runs=0)

if __name__=='__main__':print(json.dumps(main(),sort_keys=True,indent=2))
