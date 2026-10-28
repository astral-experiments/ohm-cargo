"""Create the receiver's explicit external pin set from independently read-back published files."""
import argparse,json,re,sys
from pathlib import Path
HERE=Path(__file__).resolve().parent;sys.path.insert(0,str(HERE))
from bindings import manifest,verified_file
from export import WALL_GIT,STOCK_GIT,NATIVE_GIT,WALL_B,BOOT,WALL_PARENT,CONT_GIT,STOPPED_GIT,file_sha

def describe(ref,digest,root,names):
    assert re.fullmatch('[0-9a-f]{40}',ref) and ref not in (WALL_GIT,WALL_PARENT,WALL_B,BOOT,STOCK_GIT,CONT_GIT,STOPPED_GIT,NATIVE_GIT)
    contents=manifest(root,digest);files={}
    for key,name in names.items():
        assert name in contents
        expected=file_sha(root/name);verified_file(root,contents,name,expected)
        files[key]={'path':name,'sha256':expected}
    return dict(ref=ref,manifest=digest,files=files)
def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('catalog',type=Path);p.add_argument('catalog_ref');p.add_argument('catalog_manifest')
    p.add_argument('--admission',type=Path);p.add_argument('--admission-ref');p.add_argument('--admission-manifest')
    p.add_argument('--native-file',default='admission.json');p.add_argument('--ci-file',default='ci.json');p.add_argument('--catalog-publication-file',default='catalog-publication.json')
    p.add_argument('--h2-results',type=Path);p.add_argument('--h2-ref');p.add_argument('--h2-manifest');p.add_argument('--h2-terminal-file',default='terminal.json')
    p.add_argument('--native-verifier-file',default='independent.json');args=p.parse_args()
    c=describe(args.catalog_ref,args.catalog_manifest,args.catalog,{'view_gzip':'wall-view.json.gz','terminal':'terminal.json','independent':args.native_verifier_file,'registration':'registration.json','continuation':'continuation-registration.json','before':'tree-before-resume.json','after':'physical-preservation.json','bootreg':'bootstrap-registration.json','completion':'bootstrap-completion.json'})
    aa=(args.admission,args.admission_ref,args.admission_manifest);assert all(aa) or not any(aa)
    a=describe(args.admission_ref,args.admission_manifest,args.admission,{'native':args.native_file,'ci':args.ci_file,'catalog_publication':args.catalog_publication_file,'witness':'root-native-witness.json','proof':'native-verifier.json','bootreg':'bootstrap-registration.json','completion':'bootstrap-completion.json','provenance':'provenance.json'}) if args.admission else None
    flags=(args.h2_results,args.h2_ref,args.h2_manifest);assert all(flags) or not any(flags)
    h2=None
    if args.h2_results:
        assert re.fullmatch('[a-f0-9]{40}',args.h2_ref) and args.h2_ref not in (WALL_GIT,WALL_PARENT,WALL_B,BOOT,STOCK_GIT,CONT_GIT,STOPPED_GIT,NATIVE_GIT)
        mf=args.h2_results/'SHA256SUMS';assert not mf.is_symlink() and file_sha(mf)==args.h2_manifest
        name=args.h2_terminal_file;rel=Path(name);assert not rel.is_absolute() and '..' not in rel.parts
        row,=[r.split('  ',1) for r in mf.read_text().splitlines() if r.split('  ',1)[1]==name]
        f=args.h2_results/name;assert f.is_file() and f.resolve()==args.h2_results.resolve()/name and file_sha(f)==row[0]
        host_name='host-receipts.json';hrow,=[r.split('  ',1) for r in mf.read_text().splitlines() if r.split('  ',1)[1]==host_name]
        hf=args.h2_results/host_name;assert hf.is_file() and hf.resolve()==args.h2_results.resolve()/host_name and file_sha(hf)==hrow[0]
        h2={'ref':args.h2_ref,'manifest':args.h2_manifest,'files':{'terminal':{'path':name,'sha256':row[0]},'host':{'path':host_name,'sha256':hrow[0]}}}
    assert len({v['ref'] for v in (a,c,h2) if v})==sum(bool(v) for v in (a,c,h2));print(json.dumps({'catalog':c,'admission':a,'h2':h2},sort_keys=True,indent=2))
if __name__=='__main__':main()
