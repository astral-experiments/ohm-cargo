#!/usr/bin/env python3
"""Check the compact current-compiler native and decoded ELF admission."""
from pathlib import Path
import hashlib
import json

d=Path(__file__).resolve().parent
raw=(d/"native.json").read_bytes()
assert hashlib.sha256(raw).hexdigest()=="35aae32d76ab6adef71a2356a90fd80d1862e0f4577e44d657414c54bddc1062"
data=json.loads(raw)
assert data["terminal"]=="23c340e8f4caf3648b7aed0c351751f4e2d238880f2a98ba26e9e703ed55bf07"
assert data["raw_complete_decode"]=="6d66240923768155bafd4a60c4de0f3518f9dcad2217e76a9269807212b32ce4" and data["measurement_samples"]==0
n=data["native_reference"]
assert n["source"]=="08d49cba6aacb0cac27a96eea335ed1c7439f483" and n["cargo"]=="2d44bd4aa68b9ba32cacb5a384ecc18fa5e7553c"
assert n["physical_sdk_sha256"]=="7ba48143d004779d031113a5561124bbe714f72b65590879b36e29ca59b1eaed"
for rev in "AB":
    x=data["branches"][rev]
    digest=[v["sha256"] for v in x["cli_off_on"]]
    assert n["cross_option"][rev]["raw_cli_off_on"]==digest and len(set(digest))==2
    assert x["observed_unit_dirs_off_on"]==["e857b49687267b61/out/build","409c6d41186d851a/out/build"]
    assert x["outside_permitted_equal_bytes"]=={"A":94177808,"B":94056598}[rev]
    assert len(x["load_segments_after_build_id_mask"])==4 and all(len(z["masked_a"])==64 for z in x["load_segments_after_build_id_mask"])
    assert set(x["actual_changed_sections"])=={".debug_info",".debug_macro",".debug_str",".note.gnu.build-id"}
    for sec,pair in x["actual_changed_sections"].items():
        a,b=pair["a"],pair["b"]
        assert a["sha256"]!=b["sha256"] and all(a[k]==b[k] for k in ("size","offset","flags","type","entsize"))
        assert not (a["flags"]&4) and (not sec.startswith(".debug") or not a["flags"]&2)
    for k,lines,npath in (("info",15551948 if rev=="A" else 15528403,56517),("macro",68285,0)):
        stream=x["complete_decodings"][k]
        assert stream["lines_each"]==lines and stream["matched_path_occurrences_each"]==npath
        assert stream["blocks"]==lines//65536+1
        assert len(stream["normalized_sha256"])==len(stream["ordered_65536_line_block_hashes_sha256"])==64
    for i,mode in enumerate(("off","on")):
        reference=n["native_reference"][mode]
        for phase in ("empty-A","first-B","return-A","return-B","unchanged-B"):
            if phase[-1]!=rev:continue
            y=reference[phase]
            assert y["independent_empty_full_file_equality"] and y["cli"]==x["cli_off_on"][i] and y["reader"]==x["consumer"]
            observed=(y["real_rustc"],y["real_wild"])
            assert observed==((379,69) if phase=="empty-A" else (0,0) if phase=="unchanged-B" else (20,1))
print("Verified two independent current-compiler ELF pairs, ten native visits, two additional clean builds and zero measurement samples.")
