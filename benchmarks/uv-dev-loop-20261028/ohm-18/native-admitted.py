"""Keep raw products and validate the stock ELF header variants seen in real uv unit targets."""
import importlib.util
import json
import sys
from pathlib import Path
from elf_equivalence import uv_elf

here=Path(__file__).resolve().parent
uvx='--uvx-source' in sys.argv
if uvx:sys.argv.remove('--uvx-source')
spec=importlib.util.spec_from_file_location('native_workload',here/('native-uvx.py' if uvx else 'native.py'))
native=importlib.util.module_from_spec(spec);spec.loader.exec_module(native)
raw_artifacts=native.artifacts
proven=json.loads((here/'stock-elf-forms.json').read_text())
forms={}
def check_form(path,record):
    canonical=record['canonical_sha256'];raw=record['raw_sha256']
    entsize=record['normalized_fields']['rodata'][2]
    key=(path,canonical,entsize)
    if forms.setdefault(key,raw)!=raw:
        raise ValueError(f'GNU build ID changed with identical product and sh_entsize: {path}')
def artifacts(root,ep,roster):
    chosen,extra=raw_artifacts(root,ep,roster)
    if ep!='check':
        check_form('debug/uv',extra['uv_elf'])
    if ep=='test':
        described={}
        for path in proven['test_paths']:
            if path not in chosen:
                raise ValueError(f'missing expected uv unit executable: {path}')
            record=uv_elf(root/'target'/path)
            assert record['raw_sha256']==chosen.pop(path)
            check_form(path,record)
            described[path]=record
            chosen[path+'@stock-rodata-entsize-buildid']=record['canonical_sha256']
        extra['uv_unit_ELFs']=described
    return chosen,extra
native.artifacts=artifacts
if __name__=='__main__':native.main()
