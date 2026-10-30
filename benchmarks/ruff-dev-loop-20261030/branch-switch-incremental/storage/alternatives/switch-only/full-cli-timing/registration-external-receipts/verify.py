#!/usr/bin/env python3
"""Independently reopen a calibration, or every closed receipt of a terminal stage."""
import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile
sys.path.insert(0,str(Path(__file__).resolve().parent))
from receiver import canonical,check,digest,reopen,safe_name

def j(p):return json.loads(p.read_bytes())
def hash_bytes(v):return hashlib.sha256(v).hexdigest()
def raw_manifest(path):
    proc=subprocess.Popen(["zstd","-qdc",str(path)],stdout=subprocess.PIPE)
    found={}
    try:
        with proc.stdout as f,tarfile.open(fileobj=f,mode="r|") as tar:
            for m in tar:
                # The bounded QA bundle contains only small native/calibration files.
                check(m.isreg() and safe_name(m.name)==m.name and m.name not in found and m.size<8*2**20,
                      "unexpected calibration archive member")
                with tar.extractfile(m) as v:
                    payload=v.read();check(len(payload)==m.size,"short calibration member")
                    found[m.name]=payload
        check(proc.wait()==0,"could not reopen full compressed calibration")
    finally:
        if proc.poll() is None:proc.kill();proc.wait()
    return found

def qa(root):
    check((root/"exit").read_text().strip()=="0","nonterminal calibration")
    test=j(root/"receiver-result.json");io_proof=j(root/"io-result.json");fd=j(root/"nested.json");raw=j(root/"raw.json")
    check(test["scaled_kit"] and test["measured_samples"]==0 and test["real_native_values"]==[17,29] and
          test["malformed_link_exit"]!=0 and test["physical_enospc"]["errno"]==28 and test["idempotent"] and test["preserved_existing"]
          and test["trailing_corruption_rejected"] and test["selector"]==["original","external-home","wait","wait","wait"],
          "missing fail-stop or independent selector controls")
    check(fd["scored_samples"]==0 and [v["exit"] for v in fd["observations"]]==[0,101] and
          all(v["different_mount"] and v["same_live_fds_after_disconnect"] for v in fd["observations"]),
          "separate native namespaces did not guard their open descriptors")
    file=root/"bounded-raw.tar.zst"
    check(file.stat().st_size==raw["size"] and digest(file)==raw["sha256"] and raw["all_original_bytes_reopened"],
          "closed full physical QA artifact changed")
    contents=raw_manifest(file)
    check(len(contents)==raw["members"],"missing raw rows")
    check(test["tiny_durable_on_block_device"] and test["raw_spool_full_errno"]==28 and
          json.loads(contents["spool-limit/first-stop.json"])=={"errno":28,"partial_source_retained":True},"uncalibrated physical failure")
    fsyncs=[v for v in contents["spool/receiver.trace"].decode().splitlines() if v.startswith("fsync(") and v.endswith("= 0")]
    check(any("/tiny-durable/." in v and "pending-" in v for v in fsyncs) and
          any("/tiny-durable>" in v for v in fsyncs),"missing actual fsync on the file or containing physical directory")
    check(hash_bytes(contents["work/provider/independent-success"])==test["successful_body"] and
          hash_bytes(contents["work/provider/actual-wrong"])==test["wrong_executable"] and
          test["successful_body"]!=test["wrong_executable"],"genuine output choices were conflated")
    for n in ("independent-success","actual-wrong"):
        provider="later" if n=="independent-success" else "earlier"
        check((provider+"/libselected.a").encode() in contents["work/provider/"+n+".ld.stdout"],
              "linker never reported actual provider")
    check(hash_bytes(contents["work/provider/earlier/libselected.a"])==test["malformed_bytes"] and
          b"libselected.a" in contents["work/provider/malformed.ld.stderr"],"missing actual malformed failure")
    store="receiver/store/"
    packed=[n for n in contents if n.startswith(store) and n.endswith(".commit.json")]
    with tempfile.TemporaryDirectory(prefix="verify-receiver-qa-") as tmp:
        for name in packed:
            c=json.loads(contents[name]);body=contents[store+c["path"]];path=Path(tmp)/c["path"];path.write_bytes(body)
            check(hash_bytes(body)==c["sha256"] and c["bytes"]==len(body),"wrong closed archive")
            data=reopen(path,packed_sha=c["sha256"])
            check(hash_bytes(canonical(data))==c["manifest"] and len(data["files"])==c["files"],"wrong native member ledger")
    check(any(n.startswith(store+".real-full-disk-pending-") for n in contents) and
          store+"real-full-disk.commit.json" not in contents,"ENOSPC acquired a false terminal")
    i=io_proof["contents"]
    check(i["measured_samples"]==0 and i["wrong_durable_writes_three_errno"]==[30,30,30] and i["receiver_absent"] and
          i["unprivileged"] and len(set(i["source_spool_target_devices"]))==3 and io_proof["every_named_output_after_own_blocking_wait"] and
          hash_bytes(contents["spool/parent.trace"])==io_proof["physical_wait4_and_open_trace"],
          "ordinary command output topology or physical timing syscall changed")
    check(len(i["timer_probes"]["six_independent_timer_probes"])==6 and i["timer_probes"]["contributes_scored_samples"]==0,
          "real blocking timer calibration missing")
    expected=[("cold",0,17),("edit",0,29),("fresh",0,29),("invalid",101,None),("repair",0,29)]
    for row,(phase,status,value) in zip(i["actual"],expected,strict=True):
        prefix="spool/io/"+phase+"/";proc=json.loads(contents[prefix+"cargo.process.json"])
        check((row["phase"],row["exit"],row["expected_native"])==(phase,status,value) and proc["exit"]==status and
              proc["blocking_wait"]=="wait4","warm native verdict mismatch")
        for f in proc["stdout_and_stderr"]:
            stream=contents[prefix+"cargo."+f["stream"]];check(len(stream)==f["size"] and hash_bytes(stream)==f["sha256"],"edited stream")
        if value is not None:
            compressed=contents["spool/io/bodies/"+row["elf"]+".zst"]
            restored=subprocess.run(["zstd","-qdc"],input=compressed,stdout=subprocess.PIPE,check=True).stdout
            check(hash_bytes(restored)==row["elf"],"original Rust test executable missing")
        else:
            check(b"E0308" in contents[prefix+"cargo.stdout"],"negative diagnostic lost")
    check([x["elf"] for x in i["actual"]][1:3]==[i["actual"][4]["elf"]]*2,"warm and repair are different")
    image=j(root/"image-allocation.json");a=image["after_mkfs"];b=image["reserved_after_mkfs"]
    check(a[0]==b[0]==16*2**20 and a[2]==b[2] and b[1]>=b[0],"wrong image sizing")
    return dict(measured_samples=0,whole_raw=raw,real_enospc=28,unpublished_partial_preserved=True,
       accepted_archives=len(packed),physical_non_ram_lower_fsync=test["physical_root_fsync"]["sha256"],
       source_and_kit=dict(compiler=i["compiler"],cargo=i["cargo"],physical_sdk=i["local_sdk_files"],ordinary_timer=i["blocking_timer"]),
       ordinary=[[r["phase"],r["exit"],r["expected_native"],r["elf"]] for r in i["actual"]],
       fd_reconnect=[{"exit":r["exit"],"archive":r["archive"],"files":r["files"]} for r in fd["observations"]],
       selector=test["selector"],positive_output=test["successful_body"],wrong_output=test["wrong_executable"],
       malformed_input=test["malformed_bytes"],malformed_link_exit=test["malformed_link_exit"],
       kernel_read_only_rejections=i["wrong_durable_writes_three_errno"],all_named_writes_after_blocking_wait=True,
       raw_spool_full_errno=28,external_ext4_full_errno=28,small_block_disk_file_and_directory_fsync_observed=True,
       six_unscored_timer_calibrations=6,real_coordinator_met_production_resource_rules=test["production_floors_met"],
       bounded_receiver=dict(backing="private RAM for scaled formatting and ENOSPC; separate real ext4 fsync proof",
        image_bytes=b[0],after_format_allocation=a[1],after_fallocate_allocation=b[1],unchanged_image_digest=a[2]),
       private_raw_receipts={n:digest(root/n) for n in ["receiver-result.json","io-result.json","nested.json","raw.json","image-allocation.json"]})

def store(directory,stage,original):
    sumfile=Path(__file__).resolve().parent/"SHA256SUMS"
    protocol=digest(sumfile)
    check(digest(original/"SHA256SUMS")=="84d1e273f3295c39b912f76fc5758a8ea6f98072afffa742066eb04bc6028381",
          "wrong original full CLI registration")
    entries={};ledgers={}
    for p in sorted(directory.glob("*.commit.json")):
        c=j(p);d=directory/safe_name(c["path"]);ident=p.name.removesuffix(".commit.json")
        check(d.name==ident+".tar.gz" and d.stat().st_size==c["bytes"],"invalid conditional publication marker")
        l=reopen(d,packed_sha=c["sha256"])
        check(l["protocol"]==protocol and l["tag"]==ident and hash_bytes(canonical(l))==c["manifest"] and len(l["files"])==c["files"],
              "unqualified closed data")
        entries[ident]=c["sha256"];ledgers[ident]=l
    schedule=j(original/"plan.json")["schedule"]
    want={"qualification-"+v["slot"] for v in schedule[:2]}|{"actual-native-admission","scored-pilot"}|{"scored-"+v["slot"] for v in schedule if v["stage"]=="pilot"}
    if stage=="confirmation":want.update(["scored-confirmation",*["scored-"+v["slot"] for v in schedule]])
    check(set(entries)==want,"unexpected, missing, or failed immutable stage")
    for tag,ledger in ledgers.items():
        if tag.startswith(("qualification-pilot","scored-pilot-","scored-confirmation-")):
            slot=tag.split("-",1)[1]
            check("runs/"+slot+"/completed.json" in ledger["files"] and "logs/"+slot+"/closed.json" in ledger["files"]
                  and not any(k.startswith("failure-artifacts/") for k in ledger["files"]),"incomplete or failed native slot")
    return dict(physical_archives=len(entries),independently_reopened=entries,registration=protocol,stage=stage)

if __name__=="__main__":
    ap=argparse.ArgumentParser(description=__doc__);group=ap.add_mutually_exclusive_group(required=True)
    group.add_argument("--qa",type=Path);group.add_argument("--store",type=Path)
    ap.add_argument("--original",type=Path);ap.add_argument("--stage",choices=["pilot","confirmation"])
    args=ap.parse_args();output=qa(args.qa) if args.qa else store(args.store,args.stage,args.original)
    print(json.dumps(output,indent=2,sort_keys=True))
