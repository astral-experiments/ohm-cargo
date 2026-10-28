from pathlib import Path
import json
d=json.loads((Path(__file__).resolve().parent/'summary.json').read_bytes());x=d['outcome']
assert d['public_archive_sha256']=='629abab6a87c84bb4d910549ca96a31e437e3dc9de3039fedcbb7b50d198a5e8'
assert d['native_edits_exit']==0 and all(status==0 for _,status in d['native_phases'])
assert d['early_shadow_exit']==83 and d['invalid_shadow_rc']==1
assert d['source_formats']=={'ET_REL':10432,'archive':269}
assert x['training']=='050bdcd9fff94846fd4c69f1212c8b3c66eb412cbdbec8e81138290a57ce25f0'
assert d['true_sealed_links']['training_sha256']!=d['true_sealed_links']['repeat_training_sha256']
assert d['true_sealed_links']['root_output_equal'] and d['true_sealed_links']['output_sha256']==x['expected_original']==x['restored']=='be6b9375b66036f898876d7f55d745c7ea11d028f7b106c31a273c26e2cdcef7'
assert x['before_hit'] and not x['during_hit'] and x['native_fallback_sha']==x['independent_complete_edited_sha']=='d76ef359714fc4339f053598978ec5464829f7d09adb24cdfd6defcae3fb56e8'
assert x['original_rlib_size']==33177182 and x['genuine_edit_rlib_size']==33177046 and x['original_rlib']!=x['genuine_edit_rlib']
assert x['native_fallback_listing']['tests']==200 and x['native_fallback_listing']['exit']==0
print('Original and clean-edited official ELFs, both genuine sealed runs and all stock fallback checks verified.')
