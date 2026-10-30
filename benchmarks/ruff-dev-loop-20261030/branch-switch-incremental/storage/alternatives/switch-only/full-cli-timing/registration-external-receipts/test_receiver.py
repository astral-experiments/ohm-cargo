#!/usr/bin/env python3
"""Exercise an actual distinct ext4 receiver, guarded failure and native providers."""
import argparse
import errno
import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import time
import sys
sys.path.insert(0,str(Path(__file__).resolve().parent))
from receiver import (GIB,MIB,canonical,check,check_receiver,digest,free,publish,
                      release_emergency,reopen,reserve_file,sources,storage_guards)
from select_route import choose,exclusive_record,hold_waiter,read_process
from handoff import ack,connect_and_hold,receive

PROOF=hashlib.sha256(b"zero-sample scaled external receiver QA").hexdigest()

def expected_error(fn, cls, explanation):
    try:
        fn()
    except cls as e:
        return str(e)
    raise AssertionError(explanation)

def postlink(root):
    root.mkdir()
    early=root/"earlier";late=root/"later";early.mkdir();late.mkdir()
    (root/"main.c").write_text("int selected(void); int main(void) { return selected(); }\n")
    def archive(directory, value):
        p=directory/"value.c";p.write_text(f"int selected(void) {{ return {value}; }}\n")
        subprocess.run(["cc","-c",p,"-o",directory/"value.o"],check=True)
        subprocess.run(["ar","rcs",directory/"libselected.a",directory/"value.o"],check=True)
    def link(name, expected, provider):
        out=root/name
        proc=subprocess.run(["cc",root/"main.c","-Wl,-t","-L"+str(early),"-L"+str(late),"-lselected","-o",out],
                            stdout=subprocess.PIPE,stderr=subprocess.PIPE)
        (root/(name+".ld.stdout")).write_bytes(proc.stdout)
        (root/(name+".ld.stderr")).write_bytes(proc.stderr)
        check(os.fsencode(provider) in proc.stdout+proc.stderr,"selected native path is missing from actual linker output")
        if expected is None:
            check(proc.returncode!=0,"malformed native input accepted")
            return proc.returncode
        check(proc.returncode==0 and subprocess.run([out]).returncode==expected,"native verdict")
        return out
    archive(late,17)
    gold=link("reference",17,late/"libselected.a")
    repeated=link("independent-success",17,late/"libselected.a")
    check(gold.read_bytes()==repeated.read_bytes() and gold.stat().st_ino!=repeated.stat().st_ino,
          "independent complete success")
    archive(early,29)
    wrong=link("actual-wrong",29,early/"libselected.a")
    check(wrong.read_bytes()!=gold.read_bytes(),"real wrong provider should differ")
    bad=early/"libselected.a";bad.write_bytes(b"Object does not contain a native provider.\n")
    malformed=link("malformed",None,bad)
    return gold,repeated,wrong,bad,malformed

def test_selector(testdir):
    rows=[]
    for scratch,home,expect in [(141*GIB,145*GIB,"original"),(140*GIB+20*MIB,143*GIB,"external-home"),
                                (140*GIB+8*MIB,143*GIB,"wait"),(141*GIB,140*GIB,"wait"),
                                (140*GIB+100*MIB,140*GIB+384*MIB,"wait")]:
        actual=choose(scratch,home,80*GIB,predecessors=True,ordinary_slots=0,original_release_exists=False)
        check(actual==expect,"selection precedence or strict physical floor");rows.append(actual)
    expected_error(lambda:choose(141*GIB,145*GIB,80*GIB,predecessors=True,ordinary_slots=1,original_release_exists=False),ValueError,"post-observation route change")
    source=testdir/"original";source.mkdir();(source/"runs").mkdir()
    child=subprocess.Popen([sys.executable,"-IB","-c","import time;time.sleep(120)"],stdin=subprocess.DEVNULL)
    try:
        p=read_process(child.pid)
        want=dict(pid=child.pid,argv=p["argv"],start_tick=p["start_tick"])
        bad=dict(want,start_tick=str(int(want["start_tick"])+1))
        expected_error(lambda:hold_waiter(bad,source,lambda _:None),ValueError,"wrong original process identity")
        (source/"clock-release.json").write_text("{}")
        expected_error(lambda:hold_waiter(want,source,lambda _:None),ValueError,"already released original")
        (source/"clock-release.json").unlink()
        def failure(_):
            raise RuntimeError("simulated failure before the durable selection")
        expected_error(lambda:hold_waiter(want,source,failure),RuntimeError,"failed delegate")
        end=time.monotonic()+1
        while read_process(child.pid)["state"] in ("T","t") and time.monotonic()<end:
            time.sleep(.005)
        check(read_process(child.pid)["state"] not in ("T","t"),"failed pre-selection must restore original waiter")
        selector=testdir/"one-choice.json"
        def commit(p):
            exclusive_record(selector,dict(route="external-home",old_start=p["start_tick"],old_state=p["state"]))
        hold_waiter(want,source,commit)
        check(read_process(child.pid)["state"] in ("T","t") and selector.is_file(),"unblocked old dispatcher")
        expected_error(lambda:exclusive_record(selector,{}),FileExistsError,"double selection")
    finally:
        os.kill(child.pid,signal.SIGCONT);child.terminate();child.wait()
    return rows

def test_real_fd_handoff(x, success, wrong):
    import socket
    saved=os.open(".",os.O_RDONLY|os.O_DIRECTORY)
    records=[]
    try:
        os.chdir(x.spool)
        with socket.socket(socket.AF_UNIX,socket.SOCK_SEQPACKET) as srv:
            srv.bind("actual-body.sock");srv.listen(1)
            for code,source in [(0,success),(101,wrong)]:
                slot="fd-native-"+str(code)
                pid=os.fork()
                if pid==0:
                    try:
                        srv.close()
                        rv=connect_and_hold("actual-body.sock",slot,code,{"real.elf":source})
                        os._exit(0 if rv["slot"]==slot else 5)
                    except BaseException:
                        os._exit(6)
                with srv.accept()[0] as conn:
                    msg,items,fd=receive(conn,slot,["real.elf"],owner=os.getuid(),carrier_pid=os.getpid())
                    try:
                        passed=items["real.elf"]
                        check(passed.stat().st_dev==source.stat().st_dev and passed.stat().st_ino==source.stat().st_ino
                              and msg["exit"]==code,"external receiver opened a different artifact")
                        hit=publish(x.receiver,slot,PROOF,{"failure-artifacts/native.elf":passed})
                        check(reopen(x.receiver/hit["path"],packed_sha=hit["sha256"])["files"]["failure-artifacts/native.elf"]==
                              [source.stat().st_size,digest(source)],"native body lost through namespace handoff")
                        check(os.waitpid(pid,os.WNOHANG)==(0,0),"producer closed before durable custody")
                        ack(conn,slot,hit["sha256"]);records.append([code,digest(source),hit["sha256"]])
                    finally:
                        for z in fd:os.close(z)
                check(os.waitpid(pid,0)[1]==0,"native holder failed after acknowledged publication")
    finally:
        os.fchdir(saved);os.close(saved)
    return records

def main():
    args=argparse.ArgumentParser()
    for name in ("fixture","spool","receiver","backing","scratch","image","durable_tiny_out","result","spool_limit"):
        args.add_argument(name,type=Path)
    x=args.parse_args()
    dev=check_receiver(x.receiver,x.spool,x.backing,x.scratch,x.image,max_total=17*MIB,image_size=16*MIB)
    available=int(next(line.split()[1] for line in Path("/proc/meminfo").read_text().splitlines()
                       if line.startswith("MemAvailable:")))*1024
    actual,rejected=storage_guards(Path.home(),x.scratch,available,entry=True)
    # Each independent constraint must reject a physically presented volume when its floor is raised above real free.
    base=dict(home_floor=1,scratch_floor=1,receive_margin=MIB,scratch_margin=MIB,
              entry_memory=1,live_memory=1)
    hosts=dict(home=x.backing,scratch=x.scratch,memory=100)
    _,ok=storage_guards(**hosts,entry=True,**base);check(ok,"scaled positive capacity")
    _,ok=storage_guards(**hosts,entry=True,**dict(base,home_floor=free(x.backing)));check(not ok,"independent HOME veto")
    _,ok=storage_guards(**hosts,entry=True,**dict(base,scratch_floor=free(x.scratch)));check(not ok,"independent scratch veto")
    _,ok=storage_guards(**hosts,entry=True,**dict(base,entry_memory=100));check(not ok,"independent memory veto")
    expected_error(lambda:storage_guards(x.backing,x.backing,100,entry=True,**base),ValueError,"aliased durable devices")
    small=x.spool_limit
    check(small.stat().st_dev not in dev and os.statvfs(small).f_blocks*os.statvfs(small).f_frsize==2*MIB,
          "raw spool test must use its own capped filesystem")
    emergency_spool=small/"emergency";reserve_file(emergency_spool,256*1024)
    reserve_file(small/"only-qa-filler",free(small))
    try:
        with (small/"incomplete").open("xb",buffering=0) as f:f.write(b"x"*4096)
    except OSError as e:
        check(e.errno==errno.ENOSPC,"wrong capped spool error")
    else:raise ValueError("full raw spool unexpectedly writable")
    release_emergency(emergency_spool,256*1024)
    with (small/"first-stop.json").open("xb") as f:
        f.write(canonical(dict(errno=errno.ENOSPC,partial_source_retained=True)));f.flush();os.fsync(f.fileno())
    check((small/"incomplete").is_file() and (small/"first-stop.json").is_file(),"spool failure ledger not retained")
    option=test_selector(x.fixture)
    gold,same,wrong,bad,malformed=postlink(x.fixture/"provider")
    fd_handoffs=test_real_fd_handoff(x,same,wrong)
    sp=x.spool/"runs/qualified";sp.mkdir(parents=True)
    (sp/"native.stdout").write_bytes(b"17\n");(sp/"content-addressed-success.json").write_bytes(
        canonical(dict(sha256=digest(gold),size=gold.stat().st_size,actual_sha256=digest(same),native_exit=17)))
    emergency=x.receiver/"reserved-emergency";reserve_file(emergency,2*MIB)
    files=sources(x.spool,["runs/qualified"],{"failure-artifacts/independent-success.elf":same})
    success=publish(x.receiver,"verified-native",PROOF,files,emergency=(emergency,2*MIB),hard_payload_bytes=16*MIB)
    check(reopen(x.receiver/success["path"])["files"]["failure-artifacts/independent-success.elf"][1]==digest(gold),
          "actual independent whole success")
    duplicate=publish(x.receiver,"verified-native",PROOF,files,emergency=(emergency,2*MIB))
    check(duplicate["reused"] and duplicate["sha256"]==success["sha256"],"idempotent reopen")
    # Model a crash after the data's durable link, before its marker, in a distinct QA slot.
    recovered=publish(x.receiver,"before-marker",PROOF,files,emergency=(emergency,2*MIB))
    (x.receiver/"before-marker.commit.json").unlink()
    replay=publish(x.receiver,"before-marker",PROOF,files,emergency=(emergency,2*MIB))
    check(replay["reused"] and replay["sha256"]==recovered["sha256"] and (x.receiver/"before-marker.commit.json").is_file(),
          "did not verify uncommitted data before recoverable publication")
    copy=x.spool/"altered-copy";shutil.copyfile(x.receiver/success["path"],copy)
    with copy.open("ab") as out:out.write(b"unaccounted bytes")
    expected_error(lambda:reopen(copy,packed_sha=success["sha256"]),ValueError,"altered complete archive was accepted")
    (sp/"native.stdout").write_bytes(b"changed\n")
    conflicting=expected_error(lambda:publish(x.receiver,"verified-native",PROOF,files),ValueError,"conflicting retry accepted")
    (sp/"native.stdout").write_bytes(b"17\n")
    badlink=sp/"bad-link";badlink.symlink_to(wrong)
    link_error=expected_error(lambda:sources(x.spool,["runs/qualified"]),ValueError,"symlink entered receipt");badlink.unlink()
    # Cause real kernel ENOSPC on this small, private ext4 only; never fill either physical host volume.
    large=x.spool/"uncompressible";large.write_bytes(os.urandom(3*MIB))
    previous=digest(x.receiver/success["path"])
    filler=x.receiver/"qa-exclusive-filler";reserve_file(filler,free(x.receiver)-MIB)
    failed_ledger={}
    try:
        publish(x.receiver,"real-full-disk",PROOF,{"saturated/input":large},emergency=(emergency,2*MIB))
    except OSError as e:
        check(e.errno==errno.ENOSPC,"wrong physical error");failed_ledger={"errno":e.errno,"message":e.strerror}
    else:
        raise AssertionError("full private receiving filesystem reported success")
    check(not (x.receiver/"real-full-disk.tar.gz").exists() and list(x.receiver.glob(".real-full-disk-pending-*")),
          "published an incomplete archive or lost the negative")
    check(digest(x.receiver/success["path"])==previous and large.stat().st_size==3*MIB,"lost earlier receipt or source on ENOSPC")
    # Reclaim only the artificial filler inside this test's disposable filesystem.
    filler.unlink()
    release_emergency(emergency,2*MIB)
    failure_files=sources(x.spool,["runs/qualified"],{"failure-artifacts/wrong-provider.elf":wrong,
            "failure-artifacts/malformed-provider.a":bad,
            "failure-artifacts/real-link.stderr":x.fixture/"provider/malformed.ld.stderr"})
    saved=publish(x.receiver,"genuine-wrong-provider",PROOF,failure_files,hard_payload_bytes=16*MIB)
    ledger=reopen(x.receiver/saved["path"])
    check(ledger["files"]["failure-artifacts/wrong-provider.elf"]==[wrong.stat().st_size,digest(wrong)] and
          ledger["files"]["failure-artifacts/malformed-provider.a"][1]==digest(bad),"wrong body failed independent readback")
    # Separate tiny actual disk fsync/link/reopen, in addition to the bounded ext4 test device.
    x.durable_tiny_out.mkdir()
    tiny=publish(x.durable_tiny_out,"tiny-physical-fsync",PROOF,{"actual/whole-native.elf":same},hard_payload_bytes=MIB)
    check(digest(x.durable_tiny_out/tiny["path"])==tiny["sha256"],"tiny durable lower readback")
    # Missing prospective sender data, broken tar, and external symlink must each reject.
    expected_error(lambda:reopen(large),Exception,"corrupt bytes accepted")
    source=x.spool/"dangling";source.symlink_to(x.fixture/"nonexistent")
    expected_error(lambda:publish(x.receiver,"dangling",PROOF,{"bad/input":source}),OSError,"dangling capture accepted")
    result=dict(production_floors_met=rejected,scaled_kit=True,measured_samples=0,
        actual_durable_free=actual,device_roles=dev,selector=option,positive=success,idempotent=duplicate["reused"],real_fd_handoffs=fd_handoffs,
        tiny_durable_on_block_device=Path("/sys/dev/block",f"{os.major(x.durable_tiny_out.stat().st_dev)}:{os.minor(x.durable_tiny_out.stat().st_dev)}").exists(),
        raw_spool_full_errno=28,raw_spool_emergency_ledger=True,
        committed_replacement_veto=conflicting,unsafe_source_veto=link_error,physical_enospc=failed_ledger,
        post_link_before_marker_recovery=replay["sha256"],trailing_corruption_rejected=True,
        negative_custody=saved,malformed_link_exit=malformed,preserved_existing=True,physical_root_fsync=tiny,
        successful_body=digest(gold),wrong_executable=digest(wrong),malformed_bytes=digest(bad),
        real_native_values=[17,29],source_and_runtime_complete=True)
    x.result.write_text(json.dumps(result,sort_keys=True,indent=2)+"\n")
    print(json.dumps(result,sort_keys=True))

if __name__=="__main__":
    main()
