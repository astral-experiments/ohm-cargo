"""Exercise source views, actual native archive/metadata inspection and a mutated symbol-index control without timing Cargo."""
import argparse,json,os,shutil,struct,subprocess,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
import archive_audit,common,products,state
from common import dump,need,sha
cli=argparse.ArgumentParser();cli.add_argument('--out',type=Path,required=True);cli.add_argument('--ruff',type=Path,required=True)
cli.add_argument('--native-stdout',type=Path,required=True);cli.add_argument('--old-target',type=Path,required=True);cli.add_argument('--retained-target',type=Path,required=True)
cli.add_argument('--sysroot',type=Path,required=True);cli.add_argument('--rustup',type=Path,required=True)
a=cli.parse_args();a.out.mkdir();common.RUFF=state.RUFF=a.ruff
fixture=state.inputs(a.out);st=a.out/'views';st.mkdir();(st/'inputs'/state.RSL).parent.mkdir(parents=True)
for rel in state.DELETED:
    f=st/'inputs'/rel.parent;f.parent.mkdir(parents=True,exist_ok=True);shutil.copytree(a.ruff/rel.parent,f)
token=[]
for val in (False,True,False):
    state.set_source(st,fixture,val)
    src="""import json,sys;from pathlib import Path;sys.path.insert(0,sys.argv[1]);import common,state
common.RUFF=state.RUFF=Path(sys.argv[2]);state.verify_view(sys.argv[3]=='edited',json.loads(Path(sys.argv[4]).read_bytes()));print('verified')"""
    p=subprocess.run(['bwrap','--ro-bind','/','/','--dev','/dev','--proc','/proc',*state.source_binds(st),'--',sys.executable,'-B','-c',src,str(Path(__file__).parent),str(a.ruff),'edited' if val else 'original',str(fixture/'manifest.json')],capture_output=True,text=True)
    need(p.returncode==0,('real scoped edit/restore',p.stderr));token.append(p.stdout.strip())
need(common.git('rev-parse','HEAD')==state.PIN,'underlying checkout')
products.FROZEN=a.sysroot;products.env=lambda:{**os.environ,'RUSTUP_HOME':str(a.rustup),'RUSTUP_AUTO_INSTALL':'0'}
# Fixtures already retain the large cold ELF files; additionally exercise the compressed
# durability path on a small file and calculate every actual large product digest in place.
f=fixture/'manifest.json';compressed=products.retain(f,a.out/'private-sample-compressed')
products.retain=lambda p,retained:sha(p)
raw=a.out/'local-headers';raw.mkdir();rows={};lib=None
for sl in a.native_stdout.read_bytes().splitlines():
    row=json.loads(sl)
    if row.get('reason')!='compiler-artifact' or row['target']['name'] not in state.WASM or row['profile']['test']:continue
    files=[str(a.retained_target/Path(p).relative_to(a.old_target)) for p in row['filenames']]
    witness=products.inspect_one(files,raw);lib=next(Path(p) for p in files if p.endswith('.rlib'))
    rows[row['target']['name']]={k:witness[k] for k in ('private_svh','public_svh','rmeta_sha256','embedded_object_sha256','normalized_archive_sha256','zero_byte_allocations')}
    rows[row['target']['name']].update(object_count=len(witness['archive']['objects']),symbols=witness['archive']['symbol_index_entries'])
need(set(rows)==set(state.WASM),'both actual Ruff products');origin=archive_audit.inspect(lib);blob=bytearray(lib.read_bytes())
# Substitute another real object's member ordinal under the first symbol, using this GNU archive's
# big-endian offset table. Every object/metadata payload stays exactly the same.
n=struct.unpack_from('>I',blob,68)[0];entries=struct.unpack_from('>'+str(n)+'I',blob,72)
replacement=next(x for x in entries if x!=entries[0]);struct.pack_into('>I',blob,72,replacement)
mut=a.out/'changed-index.rlib';mut.write_bytes(blob);altered=archive_audit.inspect(mut);d=archive_audit.compare(origin,altered)
need(d['same_slot_payloads']==d['object_count'] and not d['identical_ordered_symbol_to_member_index'],'symbol map control')
need(products.canonical_archive(lib,origin)!=products.canonical_archive(mut,altered),'normalized archive must retain symbol index')
mut.unlink()
dump(a.out/'rehearsal.json',{'source_manifest':common.load(fixture/'manifest.json'),'git_original_edited_original':token,'source_unchanged':True,'compressed_witness':compressed,'actual_ruff_mixed_members':rows,'changed_symbol_to_member_detected':True,'cargo_timings':0})

