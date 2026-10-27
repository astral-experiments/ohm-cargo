"""Ensure that two interchangeable basenames are resolved by the actual compiler output paths."""
from pathlib import Path
import copy,json,shutil,sys,tempfile,unittest
sys.path.insert(0,str(Path(__file__).resolve().parent))
from witness import active_records
class Paths(unittest.TestCase):
    def setUp(self):
        self.t=tempfile.TemporaryDirectory();self.addCleanup(self.t.cleanup)
        self.base=Path(self.t.name);self.r=[];self.f={'proofs':[],'active_rustc':[]}
        for role in ('active','passive'):
            unit=self.base/role/'ron'/'48dcee1813f38341';out=unit/'out';out.mkdir(parents=True);fp=unit/'fingerprint';fp.mkdir()
            md=out/'libron-48dcee1813f38341.rmeta';md.write_bytes(role.encode());d=out/'ron-48dcee1813f38341.d';d.touch();enc=fp/'dep-lib-ron';enc.touch()
            self.r.append({'name':'ron','raw':str(d),'encoded':str(enc)});self.f['proofs'].append({'raw':str(d),'encoded':str(enc),'metadata':str(md),'role':role})
            if role=='active':
                self.j={'package_id':'registry+test#ron@0.12.0','features':['default','std'],'profile':{'test':False},'target':{'name':'ron','kind':['lib']},'filenames':[str(md)]}
                self.f['active_cargo_artifact']=copy.deepcopy(self.j);self.f['active_rustc']=[{'out_dir':str(out)}]
    def run_case(self,rows=None):
        return active_records([json.dumps(r) for r in (rows or [self.j])],self.r,'test',self.f)
    def test_select_live_directory(self):
        a,p,j,md=self.run_case();self.assertEqual((a[0],p[0]),tuple(self.r));self.assertEqual([q['role'] for q in md],['active','passive'])
    def test_ambiguous_advertisements(self):
        with self.assertRaises(ValueError):self.run_case([self.j,self.j])
    def test_wrong_target_features(self):
        self.j['features']=['std']
        with self.assertRaises(ValueError):self.run_case()
    def test_wrong_matching_basename(self):
        self.j['filenames']=[self.f['proofs'][1]['metadata']];self.f['active_cargo_artifact']=copy.deepcopy(self.j)
        with self.assertRaises(ValueError):self.run_case()
    def test_lost_witness(self):
        self.r.pop()
        with self.assertRaises(ValueError):self.run_case()
    def test_mixed_fingerprint(self):
        self.r[0]['encoded']=self.r[1]['encoded']
        with self.assertRaises(ValueError):self.run_case()
if __name__=='__main__':unittest.main()
