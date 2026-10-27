"""Check each signed width and fail closed on other pairs/ELF fields."""
import json,sys
from pathlib import Path
p=Path(__file__).resolve().parent
sys.path.insert(0,str(p))
from elf_gate import permitted_linker_width
def extract(r):
    return dict(rodata_entsize=r["rodata_entsize"],rodata_type=1,rodata_flags=r["rodata_flags"],bytes=r["size"],except_registered_wild_fields=r["normalized"],build_id=r["build_id"])
controls=json.loads((p/"stock-widths.json").read_bytes())["inputs"]
pairs=0
for n in (1,2,4,8,16,32,64,128,256):
    a,b=map(extract,controls[str(n)]["observations"][:2]);assert permitted_linker_width(a,b) and permitted_linker_width(b,a);pairs+=2
    assert not permitted_linker_width(a,a) and not permitted_linker_width(b,b)
    for k,v in (("bytes",b["bytes"]+1),("build_id",a["build_id"]),("build_id","ab"),("except_registered_wild_fields","0"*64),("rodata_type",2),("rodata_flags",1),("rodata_entsize",3),("rodata_entsize",512)):
        assert not permitted_linker_width(a,dict(b,**{k:v}))
    assert not permitted_linker_width(dict(a,rodata_flags=2),dict(b,rodata_flags=2))
    assert not permitted_linker_width(dict(a,rodata_flags=0x13),dict(b,rodata_flags=0x13))
    assert not permitted_linker_width(dict(a,rodata_flags=0x16),dict(b,rodata_flags=0x16))
    assert not permitted_linker_width(dict(a,rodata_entsize=1),dict(b,rodata_entsize=8))
print(f"{pairs} signed original-Wild field contrasts accepted; differing bytes, untraced ELF types/flags, unsupported widths and nonzero-to-nonzero contrasts rejected.")
