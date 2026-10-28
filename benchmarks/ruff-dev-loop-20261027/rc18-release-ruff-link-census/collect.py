"""Collect public fields and SHA-256 commitments from an already completed on-disk cohort."""
import ast
import errno
import gzip
import hashlib
import json
import os
import stat
import re
import sys
from collections import Counter
from pathlib import Path

root = Path(sys.argv[1]).expanduser().resolve(strict=True)
reports = root / "reports"
raw = {}
sha = lambda data: hashlib.sha256(data).hexdigest()


def take(path):
    data = path.read_bytes()
    raw[path.relative_to(root).as_posix()] = sha(data)
    return data


def load(path):
    return json.loads(take(path))


def namespace(path):
    return next(part for part in Path(path).parts if re.fullmatch(r"v2-[a-f0-9]{16}", part))


def shadow_search(argv):
    choices = [value[2:] for value in argv if value.startswith("-L") and "psm" in Path(value[2:]).parts]
    assert len(set(choices)) == 1
    return namespace(choices[0])


def end(label, expected):
    p = root / "jobs" / label
    assert int(take(p / "exit")) == expected
    return {"exit": expected, "stdout": sha(take(p / "stdout")), "stderr": sha(take(p / "stderr"))}


def events(folder):
    trace = {}
    native = []
    modes = Counter()
    for f in sorted((folder / "trace").glob("e.*")):
        data = f.read_bytes()
        trace[f.name] = sha(data)
        for line in data.splitlines():
            if not line.startswith(b'execve("') or not line.endswith(b'= 0'):
                continue
            match = re.fullmatch(rb'execve\(("(?:\\.|[^"\\])*"), (\[.*\]), (?:0x[\da-f]+|NULL).*?\)\s+= 0', line)
            assert match
            path = Path(ast.literal_eval(match[1].decode()))
            if path.name == "ld.bfd" and path.parent.name == "wild-ld":
                argv = ast.literal_eval(match[2].decode())
                out = argv[argv.index("-o") + 1]
                native.append({"target": Path(out).name, "output_namespace": namespace(out),
                               "search_namespace": shadow_search(argv), "trace_file": f.name, "trace_sha256": trace[f.name]})
            elif path.name == "rustc":
                argv = ast.literal_eval(match[2].decode())
                if "--crate-name" in argv:
                    modes["link-only" if "-Zlink-only" in argv or "link-only" in argv else "full"] += 1
    return {"successful_native_execs": sorted(native, key=lambda item: item["target"]),
            "rustc_counts": dict(modes), "all_trace_files": len(trace),
            "raw_trace_set_sha256": sha(json.dumps(trace, separators=(",", ":"), sort_keys=True).encode())}


def stream(phase):
    stdout = take(phase / "cargo.stdout")
    stderr = take(phase / "cargo.stderr")
    messages = [json.loads(line) for line in stdout.splitlines()]
    assert messages[-1]["reason"] == "build-finished"
    return {"cargo_success": messages[-1]["success"],
            "units": sum(x["reason"] == "compiler-artifact" for x in messages),
            "finished_stdout_sha256": sha(stdout), "stderr_sha256": sha(stderr),
            "has_malformed_provider_diagnostic": all(x in stdout + stderr for x in
            (b"OHM_REJECT_BAD_WORKSPACE_TEST_LINK_SCRIPT", b"libgcc_s.so"))}


def original_packet(group):
    archive = reports / ("public-release-" + group) / "cohort.json.gz"
    study = json.loads(gzip.decompress(take(archive)))
    for label, phase in study["phases"].items():
        folder = reports / phase["label"]
        for filename, expected in phase["private_original_sha256"].items():
            assert sha(take(folder / filename)) == expected
        original = load(folder / "result.json")
        exit_code = load(folder / "exit.json")
        assert exit_code["status"] == 0
        for key in ("units", "fresh", "native", "e2e_sha256", "test_results", "e2e_size"):
            assert original[key] == phase[key]
        messages = [json.loads(line) for line in (folder / "cargo.stdout").read_bytes().splitlines()]
        artifacts = [m for m in messages if m["reason"] == "compiler-artifact"]
        assert messages[-1] == {"reason": "build-finished", "success": True}
        assert (len(artifacts), sum(x["fresh"] for x in artifacts)) == (phase["units"], phase["fresh"])
        classified = load(folder / "native.json")
        assert [{"kind": e["kind"], "id": Path(e["id"]).name, "argv_sha256": e["argv_sha256"]} for e in classified] == phase["executed"]
        assert Counter(x["kind"] for x in classified) == phase["native"]
        assert len((folder / "list.stdout").read_bytes().splitlines()) == phase["listed"] == 200
        assert sha(take(folder / "list.stdout")) == phase["test_list_sha256"]
    take(reports / ("release-" + group + "-summary") / "result.json")
    return sha(archive.read_bytes())


def raw_links(label):
    folder = reports / label
    capture = load(folder / "result.json")
    out = {k: capture[k] for k in ("units", "native_counts", "ty_e2e", "stock_linker", "gross_explicit_input_bytes",
                                      "union_explicit_input_bytes", "unique_explicit_paths")}
    out["records"] = []
    for row in capture["results"]:
        leaf = folder / "actual" / (str(row["pid"]) + ".json")
        actual = load(leaf)
        assert Path(actual["out"]).name == row["file"]
        assert len(actual["argv"]) == row["argv_fields"] and len(actual["persistent_operands"]) == row["persistent_explicit_operands"]
        out["records"].append({"target": row["file"], "scope": row["scope"], "sha256": row["sha256"], "size": row["size"],
                "argv_fields": row["argv_fields"], "explicit_operands": row["persistent_explicit_operands"],
                "raw_exec_sha256": sha(leaf.read_bytes()), "output_namespace": namespace(actual["out"]),
                "search_namespace": shadow_search(actual["argv"])})
    out["records"].sort(key=lambda row:row["target"])
    take(folder / "cargo.stderr")
    assert stream(folder)["units"] == capture["units"]
    return out


def output_record(row):
    return {**{k:v for k,v in row.items() if k != "output"}, "target": Path(row["output"]).name,
            "namespace": namespace(row["output"])}


def outer_run():
    folder = reports / "public-installer-all-50-native-shadow"
    data = load(folder / "result.json")
    out = {k: data[k] for k in ("targets", "wild", "original_target_unchanged", "hook_sha256")}
    assert data["before"] == load(folder / "before.json")
    take(folder / "reused-clone-before.json")
    out["before"] = [output_record(row) for row in data["before"]]
    out["mask_namespace"] = namespace(data["shadow_anchor"])
    out["phases"] = []
    for original in data["phases"]:
        phase = folder / original["phase"]
        assert original == load(phase / "result.json")
        item = {k:v for k,v in original.items() if k!="outputs"}
        if "outputs" in original:
            item["outputs"] = [output_record(row) for row in original["outputs"]]
        item["streams"] = stream(phase)
        item["processes"] = events(phase)
        out["phases"].append(item)
    return out


def release_inputs():
    names = ["ohm-1.99.0-18.json", "ohm-installer.sh", "ohm-1.99.0-18-x86_64-unknown-linux-gnu-provenance.json"]
    incoming = root / "incoming"
    name = "ohm-1.99.0-18-x86_64-unknown-linux-gnu.tar.gz"
    digest, spelling = take(incoming / (name + ".sha256")).decode().split()
    assert spelling == name
    prot = load(root / "protected-linux-installed.json")
    outer = load(root / "public-independent-install.json")
    assert digest == outer["published_archive_sha256"] == prot["archive_sha256"]
    assert prot["versions"] == outer["versions"] and prot["images"] == outer["images"]
    published = {n: sha(take(incoming / n)) for n in names}
    assert published["ohm-installer.sh"] == outer["public_installer_sha256"]
    fall = root / "prepublished/12845628355"
    pr = names[-1]
    assert take(fall / pr) == take(incoming / pr)
    assert take(fall / (name + ".sha256")) == take(incoming / (name + ".sha256"))
    provenance = load(incoming / pr)
    assert published[names[0]] == provenance["manifest"]["sha256"]
    return {"download": {"name": name, "bytes": (incoming / name).stat().st_size, "sha256": digest,
                         "additional_files": published, "provenance": provenance},
            "inner_installer_sha256": prot["inner_installer_sha256"], "outer_comparison": outer}


def observer():
    directory = root / "saved/release-qa-default/target/debug/build/workspaces"
    depfile, = directory.glob("*/*/ron/*/out/ron-*.d")
    fingerprint = depfile.parent.parent / "fingerprint/dep-lib-ron"
    dependency_text, record = take(depfile), take(fingerprint)
    marker = b"/ohm-foreign-span-bytes"
    assert stat.S_ISREG(depfile.stat().st_mode) and dependency_text.count(marker) == 4
    try:
        os.stat(str(depfile) + marker.decode())
    except NotADirectoryError as error:
        assert error.errno == errno.ENOTDIR
    else:
        raise AssertionError("expected a regular depfile")
    assert record[-41:-37] == b"OBS1" and record[-33] == 0
    return {"unit": depfile.stem, "namespace": namespace(depfile), "depfile_bytes": len(dependency_text),
            "depfile_sha256": sha(dependency_text), "marker_occurrences": dependency_text.count(marker),
            "marker_stat_errno": errno.ENOTDIR, "record_length": len(record), "record_sha256": sha(record),
            "record_magic": record[-41:-37].decode(), "record_complete_byte": record[-33]}


assert end("public-installer-actual-native-controls", 0)["exit"] == 0
sources = load(root / "prepared.json")
subject = {k:sources[k] for k in ("source","file","old_sha256","edited_sha256","historical_fix","index_sha256","registry_id_digest")}
scopes = {g: original_packet(g) for g in ("workspace", "focused")}
captures = {name: raw_links(label) for name,label in (("inner", "release-workspace-raw"),
                                                      ("outer", "public-installer-workspace-raw"))}
width = load(reports / "release-stock-widths-repeat/result.json")
width = {"distribution": width["distribution"], "logging": width["logging"],
         "samples": [{**{k:v for k,v in x.items() if k != "file"}, "target": Path(x["file"]).name,
                      "namespace": namespace(x["file"])} for x in width["results"]]}
negative = reports/"release-all-50-native-shadow"
assert not (negative/"result.json").exists()
early = {"job": end("actual-native-shadow-and-chronology", 1), "captured_before": len(load(negative/"before.json")),
         "cargo": stream(negative/"valid"), "processes": events(negative/"valid")}
assert b'results["exit_83"]>=1' in (root/"jobs/actual-native-shadow-and-chronology/stderr").read_bytes()
chrono_dir = reports / "public-installer-stock-process-chronology"
chrono = load(chrono_dir / "result.json")
gate = {k:chrono[k] for k in ("exit","units","counts","stock_touched_original_50","e2e_ran_wild","small_ran_wild","e2e_tests","e2e_list_sha256")}
gate["e2e_before_elf"] = chrono["e2e_before"]["sha256"]
gate["e2e_after_elf"] = chrono["e2e_after"]["sha256"]
gate["streams"] = stream(chrono_dir)
for name in ("execs.json", "native.json", "image-contract.json", "smallest-result.json", "notebook-0.stdout","notebook-0.stderr","notebook-1.stdout","notebook-1.stderr"):
    take(chrono_dir/name)
jobs = {name:end(name,code) for name,code in (("actual-linux-focus-then-workspace",0),("release-focused-public-cohort",0),
        ("compare-public-release-installer",1),("verify-public-runtime-and-install-ledgers",0),
        ("public-installer-actual-native-controls",0),("published-width-first-warm-repeat",0))}
packet = {"schema":1, "subject":subject, "package":release_inputs(), "original_packets":scopes,
          "live_native_captures":captures, "widths":width, "wrong_namespace":early, "active_shadow":outer_run(),
          "post_restore_chronology":gate, "observer":observer(), "jobs":jobs, "raw":raw}
print(json.dumps(packet, indent=2, sort_keys=True))
