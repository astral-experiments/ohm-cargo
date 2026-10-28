"""Match the two exact Cargo toolchain-directory names only in typed product paths."""
from pathlib import PurePosixPath
import json

ROOT = "/mnt/devbox-scratch/dev-user/ohm-spaced-ruff-20261027/logical/"
LAYOUT = {
    "package": ("ruff target", "6adf5abf43073fa3", "219e1f6eacee2500", "4fb31a41b61c56b4"),
    "workspace": ("ruff-target", "2abf155240aec459", "d23031a6115abf10", "26fd4b9f9691cd6c"),
}
MARK = "@matched-compiler@"

def key(w, arm, name):
    target, workspace, b, c = LAYOUT[w]
    assert arm in ("B", "C") and MARK not in name
    path = PurePosixPath(name)
    assert str(path) == name and ".." not in path.parts
    absolute = path.is_absolute()
    base = PurePosixPath(ROOT) / target
    if absolute:
        assert path.is_relative_to(base), name
        path = path.relative_to(base)
    parts = path.parts
    if parts[:3] == ("debug", "build", "workspaces"):
        assert len(parts) >= 6 and parts[3:5] == (workspace, "v2-" + (b if arm == "B" else c)), name
        path = PurePosixPath(*parts[:4], MARK, *parts[5:])
    return str(base / path if absolute else path)

def units(w, arm, encoded):
    rows = []
    for row in encoded:
        v = json.loads(row)
        v["filenames"] = [key(w, arm, n) for n in v["filenames"]]
        if v["executable"] is not None:
            v["executable"] = key(w, arm, v["executable"])
        rows.append(json.dumps(v, sort_keys=True, separators=(",", ":")))
    return sorted(rows)

def products(w, arm, raw):
    result = {key(w, arm, n): n for n in raw}
    assert len(result) == len(raw)
    return result

def selftest():
    for w, (target, workspace, b, c) in LAYOUT.items():
        start = ROOT + target + "/debug/build/workspaces/" + workspace + "/v2-"
        end = "/ruff/abcd/out/ruff-abcd"
        bp, cp = start+b+end, start+c+end
        assert key(w, "B", bp) == key(w, "C", cp)
        assert key(w, "B", bp) != key(w, "C", cp+"e")
        assert key(w, "B", bp.replace("/abcd/", "/bbcd/")) != key(w, "C", cp)
        assert key(w, "B", ROOT+target+"/debug/ruff") == ROOT+target+"/debug/ruff"
        for invalid in (cp, bp.replace(workspace, "0000000000000000"), bp.replace(target, "elsewhere"), bp+"/../ruff"):
            try:
                key(w, "B", invalid)
            except AssertionError:
                pass
            else:
                raise AssertionError(invalid)
        row = dict(filenames=[bp], executable=bp, manifest_path=bp, target=dict(src_path=bp), features=["literal:"+bp])
        other = dict(row, filenames=[cp], executable=cp)
        assert units(w,"B",[json.dumps(row)]) == units(w,"C",[json.dumps(other)])
        for k, value in (("manifest_path",cp), ("target",dict(src_path=cp)), ("features",["literal:"+cp])):
            assert units(w,"B",[json.dumps(row)]) != units(w,"C",[json.dumps(dict(other, **{k:value}))])
    return True
