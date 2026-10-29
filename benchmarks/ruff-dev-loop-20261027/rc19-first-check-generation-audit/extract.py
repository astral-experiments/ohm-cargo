"""Select the six authenticated Cargo checks without copying private compiler arguments."""
import hashlib
import json
import re
import sys
from collections import Counter, defaultdict
from decimal import Decimal
from pathlib import Path


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def phase(directory, identities, expected_images):
    native = json.loads((directory / "native.json").read_bytes())
    status = json.loads((directory / "status.json").read_bytes())
    assert native["root_exit"] == status["rc"] == 0
    assert native["images"] == expected_images
    assert status["stdout_sha256"] == digest(directory / "cargo.jsonl")
    assert status["stderr_sha256"] == digest(directory / "stderr")

    messages = [json.loads(x) for x in (directory / "cargo.jsonl").read_bytes().splitlines()]
    assert messages[-1] == {"reason": "build-finished", "success": True}
    assets = [x for x in messages if x["reason"] == "compiler-artifact"]
    assert not [x for x in messages if x["reason"] == "compiler-message" and x["message"]["level"] == "error"]
    text = (directory / "stderr").read_text()
    stale = set(re.findall(r"dependency on `(\w+)` is newer than we are (\d+\.\d+)s > (\d+\.\d+)s \"[^\"]+/crates/(\w+)\"", text))
    marker = sorted(set(re.findall(r'/(ty_python_semantic-[0-9a-f]+\.d/ohm-foreign-span-bytes)"', text)))
    dirty_roots = []
    for consumer, dependency, when, previous in sorted((c, d, m, n) for d, m, n, c in stale):
        delta = int((Decimal(when) - Decimal(previous)) * 10**9)
        dirty_roots.append(dict(consumer=consumer, dependency=dependency, dependency_mtime=when, consumer_mtime=previous, delta_ns=delta))

    changes = defaultdict(list)
    pattern = r"^\s*([\d.]+)s\s+INFO cargo::compiler::fingerprint: early_cutoff: unit UnitIndex\((\d+)\) built with unchanged public API hash v1:([0-9a-f]+)([^\n]*)"
    for m in re.finditer(pattern, text, re.MULTILINE):
        changes[m[3]].append(dict(unit=int(m[2]), terminal_log_ns=int(Decimal(m[1])*10**9), changed_dependency="metadata dependency changed" in m[4]))
    n = {x["pid"] for x in native["events"]}
    assert n == {int(k) for k in native["process_exit"]}
    assert not any(native["process_exit"].values())
    counts = Counter(x["role"] for x in native["events"])
    assert counts["cargo"] == 1 and counts["rustc-link-only"] == 0
    physical = []
    product_lookup = {}
    workspace = {}
    for event in native["events"]:
        if event["role"] != "rustc-full":
            continue
        argv = event["argv"]
        assert hashlib.sha256(b"\0".join(a.encode() for a in argv)+b"\0").hexdigest() == event["argv_sha256"]
        emit, = [a.removeprefix("--emit=") for a in argv if a.startswith("--emit=")]
        assert "dep-info" in emit.split(",")
        stem = next(v.split("=",1)[1] for v in argv if v.startswith("extra-filename=")).removeprefix("-")
        kind = [argv[i+1] for i,x in enumerate(argv) if x == "--crate-type"]
        ext = [argv[i+1].split("=",1)[-1] for i,x in enumerate(argv) if x == "--extern"]
        data = dict(crate=event["target"], emit=emit, kind=kind, extra_filename=stem, argv_sha256=event["argv_sha256"])
        physical.append(data)
        if event["target"] == "ruff_python_index":
            data["extern_ast"] = next(Path(x).name for x in ext if Path(x).name.startswith("libruff_python_ast-"))
            data["early_metadata_requested"] = "-Zohm-early-metadata" in argv
        side = identities.get(event["argv_sha256"])
        if not side:
            continue
        assert (side["name"], side["stem"], side["kind_indices"]) == (event["target"], stem, kind)
        h = side["public_hash"]
        assert h["version"] == 1
        rows = changes[h["value"]]
        if len(rows) != 1:
            continue
        row = dict(rows[0],public_hash=h["value"])
        data["completed_unchanged_local_hash"] = row
        key = (Path(argv[argv.index("--out-dir")+1]), stem)
        assert key not in product_lookup
        product_lookup[key] = row["unit"]
        workspace[row["unit"]] = (event["target"], row["terminal_log_ns"], ext)
    early = []
    for u,(name,finish,ext) in workspace.items():
        for x in ext:
            operand = Path(x)
            if operand.suffix != ".rmeta":
                continue
            producer = product_lookup.get((operand.parent, operand.stem.rsplit("-",1)[-1]))
            if producer is None:
                continue
            pname,pfinish,_ = workspace[producer]
            if pfinish > finish:
                early.append(dict(consumer=name,producer=pname,consumer_unit=u,producer_unit=producer,
                                  terminal_log_gap_ns=pfinish-finish,extern=operand.name))
    evidence_files = ("cargo.jsonl","stderr","native.json","status.json")
    return dict(raw_sha256={name:digest(directory/name) for name in evidence_files},
                typed_artifacts=len(assets),typed_fresh=sum(x["fresh"] for x in assets),
                native_roles=dict(counts),rustcs=physical,all_observed_processes_succeeded=True,
                missing_marker=marker,stale_mtime_edges=dirty_roots,early_completion_edges=sorted(early,key=lambda x:(x["consumer"],x["producer"])),
                unique_sidecar_and_terminal_joins=len(workspace))


def main():
    raw, sidecars, destination = map(Path, sys.argv[1:])
    subject=json.loads((raw/"tools.json").read_bytes())
    images=json.loads((raw/"images.json").read_bytes())["images"]
    assert images["cargo"]["sha256"] == subject["cargo"]
    assert images["rustc"]["sha256"] == subject["rustc"]
    ids=json.loads(sidecars.read_bytes())["rows"]
    phases={name:phase(raw/name,ids,images) for direction in ("parent","child")
            for name in (direction+"-edit",direction+"-unchanged-1",direction+"-unchanged-2")}
    exported=dict(cargo_sha256=subject["cargo"],rustc_sha256=subject["rustc"],cargo_source="235f9228651b74c591e6f62cae4c9b761448dd2d",
                  stock_sdk=subject["stock_release"],tools_sha256=digest(raw/"tools.json"),image_inventory_sha256=digest(raw/"images.json"),
                  later_sidecar_projection_sha256=digest(sidecars),phases=phases)
    destination.write_text(json.dumps(exported,indent=2,sort_keys=True)+"\n")


if __name__ == "__main__":
    main()
