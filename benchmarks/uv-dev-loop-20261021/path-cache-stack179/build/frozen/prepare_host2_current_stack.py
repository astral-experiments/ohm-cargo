#!/usr/bin/env python3
"""Freeze the separately authorized three-variant current-stack build cohort."""

import ast
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile


ROOT = Path(__file__).resolve().parent
REPO = ROOT.parent / "ohm-cargo"
COHORT = ROOT / "host2-current-stack"
PINNED = "5e5d271d763d7beb38b48755e22bd59e93f02b97"
INITIAL_TREE = "ec684868eed8347beeb23d1a998e7f2cb997bc7a"
ORDER = ("stack179-current", "stack179-path-cache", "stack176-current")
TREES = {
    "stack179-current": "f4ce59f92aa17461fe3c8b68923c88539136045a",
    "stack179-path-cache": "0a392258c801cff734d223a3f9af73d5b5a4e3c0",
    "stack176-current": "06123b7a4dfa10de0abf3b5ccd520e34172bc208",
}
REFS = {
    "stack179-current": "19718e6d1637244ffbb193334f50bae3ffca1be5",
    "stack179-path-cache": TREES["stack179-path-cache"],
    "stack176-current": "5a16c750eba7f6b7bcfd7a220a377685c62b3512",
}
HASHES = {
    "stack179-current.patch": "5db5e4a8b09ffea58d8ee7f297d2d486c7bde0d159fe51e5adcb23db72bbb573",
    "stack179-path-cache.patch": "c6903b9c8d161553d8993b35744186a840163431f2da741c516bd12ae11b6435",
    "stack176-current.patch": "c93b0fb675f90f149fc6fa766c22ce885a37d2b4b163539009dba347711c198d",
}
INCREMENTAL_HASH = "0706ae28f7cfb62774755aec611689eda86c5080846e1e37b33e5bfc60163aa9"


def sha(data):
    return hashlib.sha256(data).hexdigest()


def git(*args, env=None):
    return subprocess.check_output(["git", "-C", str(REPO), *args], env=env)


if COHORT.exists():
    raise SystemExit("refusing to overwrite an existing frozen cohort")
source_manifest = json.loads((ROOT.parent / "path-cache-publication/current-stack-build-patches.json").read_text())
old_inputs = json.loads((ROOT / "host2/frozen/manifest.json").read_text())
files = {}
expected = {}
for name in ORDER:
    description = source_manifest[name]
    assert description["ref"] == REFS[name]
    filename = name + ".patch"
    data = Path(description["path"]).read_bytes()
    assert sha(data) == description["sha256"] == HASHES[filename]
    assert git("rev-parse", REFS[name] + "^{tree}").decode().strip() == TREES[name]
    files[filename] = data
    with tempfile.TemporaryDirectory(prefix="stack-tree-", dir=ROOT) as temporary:
        environment = dict(os.environ, GIT_INDEX_FILE=str(Path(temporary) / "index"))
        git("read-tree", PINNED, env=environment)
        git("apply", "--cached", description["path"], env=environment)
        assert git("write-tree", env=environment).decode().strip() == TREES[name]
        canonical = git("diff", "--cached", "--binary", "--full-index", "--no-ext-diff", "--no-textconv", PINNED, env=environment)
    files[name + ".source.patch"] = canonical
    expected[name] = {"base": PINNED, "tree": TREES[name], "source_content_ref": REFS[name],
                      "patch_sha256": {filename: HASHES[filename]},
                      "canonical_diff_sha256": sha(canonical)}
incremental = ROOT.parent / "patches/path-cache-stack179.patch"
assert sha(incremental.read_bytes()) == INCREMENTAL_HASH
with tempfile.TemporaryDirectory(prefix="stack-incremental-", dir=ROOT) as temporary:
    environment = dict(os.environ, GIT_INDEX_FILE=str(Path(temporary) / "index"))
    git("read-tree", REFS["stack179-current"], env=environment)
    git("apply", "--cached", str(incremental), env=environment)
    assert git("write-tree", env=environment).decode().strip() == TREES["stack179-path-cache"]
files["path-cache-stack179.incremental.patch"] = incremental.read_bytes()

driver = (ROOT / "host2/frozen/build_driver_host2_pr175_sbom.py").read_text()
assert sha(driver.encode()) == old_inputs["driver_sha256"]
driver = driver.replace("host2-pr175-sbom", "host2-current-stack")
driver = driver.replace("build_driver_host2_pr175_sbom.py", "build_driver_host2_current_stack.py")


def once(before, after):
    global driver
    assert driver.count(before) == 1, (before, driver.count(before))
    driver = driver.replace(before, after)


def assign(name, value):
    line = next(line for line in driver.splitlines() if line.startswith(name + " = "))
    once(line, name + " = " + repr(value))


assign("VARIANTS", tuple((name, (name + ".patch",)) for name in ORDER))
assign("PATCH_HASHES", HASHES)
assign("EXPECTED_TREES", TREES)
once("EXPECTED_TREES = " + repr(TREES),
     "EXPECTED_TREES = " + repr(TREES) + "\nSOURCE_REFS = " + repr(REFS))
once('for name in ("status-host2-current-stack.json", "provenance-host2-current-stack.json"):',
     'for name in ("status-host2-current-stack.json", "provenance-host2-current-stack.json",\n'
     '                 "host2-current-stack.prior-binary-manifest.json"):')
once('    if current_source_tree() != TREE:\n'
     '        raise RuntimeError("initial source differs from the pinned source bundle")\n'
     '    previous_manifest = {}',
     '''    previous_status = json.loads((ROOT / "status-host2-pr175-sbom.json").read_text())
    if previous_status["state"] != "complete" or previous_status["completed_variants"] != ["pr175", "pr175-lazy-sbom"]:
        raise RuntimeError("the original host2 pair has not completed successfully")
    if current_source_tree() != "''' + INITIAL_TREE + '''":
        raise RuntimeError("initial source differs from the completed SBOM build")
    previous_manifest = json.loads((ROOT / "binaries/manifest.json").read_text())
    if set(previous_manifest) != {"cargo-pr175", "cargo-pr175-lazy-sbom"}:
        raise RuntimeError("unexpected preceding binary manifest")
    for filename, expected_hash in previous_status["sealed_artifact_sha256"].items():
        if sha(ROOT / filename) != expected_hash:
            raise RuntimeError(f"preceding artifact changed: {filename}")
    original_manifest = dict(previous_manifest)
    prior_manifest_path = ROOT / "host2-current-stack.prior-binary-manifest.json"
    with prior_manifest_path.open("xb") as stream:
        stream.write((ROOT / "binaries/manifest.json").read_bytes())''')
once('    preserved_paths = [ROOT / filename for filename in (\n'
     '        "reference-host7-provenance.json", "pinned.bundle", "pr175.patch", "lazy-sbom.patch",\n'
     '        "host2-current-stack-inputs.json", "build_driver_host2_current_stack.py", "tools/strip_binaries.py")]\n'
     '    preserved_artifacts = {str(path.relative_to(ROOT)): sha(path) for path in preserved_paths}',
     '''    preserved_paths = [ROOT / filename for filename in (
        "reference-host7-provenance.json", "pinned.bundle", "pr175.patch", "lazy-sbom.patch",
        "host2-pr175-sbom-inputs.json", "build_driver_host2_pr175_sbom.py",
        "status-host2-pr175-sbom.json", "provenance-host2-pr175-sbom.json",
        "host2-current-stack-inputs.json", "build_driver_host2_current_stack.py",
        "host2-current-stack.prior-binary-manifest.json", "tools/strip_binaries.py")]
    preserved_paths += [ROOT / filename for filename in PATCH_HASHES]
    preserved_paths += [ROOT / filename for filename in previous_status["sealed_artifact_sha256"]]
    preserved_artifacts = {str(path.relative_to(ROOT)): sha(path) for path in preserved_paths}''')
once('    provenance["upstream_patch_commit"] = "efc8b51502f8a8d1fe76997dc984481edde2740e"',
     '    provenance["source_revision_by_variant"] = SOURCE_REFS')
once('    provenance["source_import"] += "; exact PR175 patch atop pinned HEAD keeps embedded identity fixed"',
     '    provenance["source_import"] += "; frozen current-stack source-tree patches atop pinned HEAD keep embedded identity fixed"\n'
     '    provenance["preceding_manifest_records"] = original_manifest')
once('    binary_manifest = {}\n    sealed_artifacts = {}',
     '    binary_manifest = dict(previous_manifest)\n    sealed_artifacts = {}')
once('            index_path = ROOT / "tmp" / f"{variant}.source.index"',
     '''            # Make any newly added files visible to the next hard reset while
            # retaining the same unstaged patch policy for existing source files.
            subprocess.run(["git", "-C", str(SOURCE), "add", "--intent-to-add", "--all"], check=True)
            index_path = ROOT / "tmp" / f"{variant}.source.index"''')
before = '["git", "-C", str(SOURCE), "diff", "--cached", "--binary"]'
assert driver.count(before) == 2
driver = driver.replace(before, '["git", "-C", str(SOURCE), "diff", "--cached", "--binary", "--full-index", "--no-ext-diff", "--no-textconv", PINNED]')
once('                "upstream_patch_commit": "efc8b51502f8a8d1fe76997dc984481edde2740e",',
     '                "source_content_ref": SOURCE_REFS[variant],')
once('        status["sealed_artifact_sha256"] = sealed_artifacts',
     '''        if json.loads((ROOT / "binaries/manifest.json").read_text()) != binary_manifest:
            raise RuntimeError("on-disk binary manifest changed during the batch")
        if any(binary_manifest.get(name) != old for name, old in original_manifest.items()):
            raise RuntimeError("preceding cohort records changed")
        status["preserved_manifest_records_verified"] = len(original_manifest)
        status["sealed_artifact_sha256"] = sealed_artifacts''')
once('executable.startswith(("callgrind-", "cachegrind-"))',
     'executable.startswith(("cargo-", "rustc-", "callgrind-", "cachegrind-"))')
ast.parse(driver)
files["build_driver_host2_current_stack.py"] = driver.encode()

collector = (ROOT / "host2/collect_variant.py").read_text()
collector = collector.replace("host2-pr175-sbom", "host2-current-stack")
collector = collector.replace('{"pr175", "pr175-lazy-sbom"}', repr(set(ORDER)))
collector = collector.replace("{'pr175','pr175-lazy-sbom'}", repr(set(ORDER)))
ast.parse(collector)
files["collect_variant.py"] = collector.encode()

audit = (ROOT / "host2/audit.py").read_text()
audit = audit.replace("host2-pr175-sbom", "host2-current-stack")
audit = audit.replace("build_driver_host2_pr175_sbom.py", "build_driver_host2_current_stack.py")
audit = audit.replace('"cargo-pr175.build.json"', '"cargo-stack179-current.build.json"')
audit = audit.replace('rustc_settings(RESULTS, "pr175")', 'rustc_settings(RESULTS, "stack179-current")')
audit = audit.replace('if variant == "pr175-lazy-sbom":', 'if variant == "stack176-current":')
audit = audit.replace('== 14\n', '== 21\n        assert status["preserved_manifest_records_verified"] == 2\n')
audit = audit.replace('    assert record["patch_sha256"] == expected["patch_sha256"]',
                      '    assert record["patch_sha256"] == expected["patch_sha256"]\n'
                      '    assert record["source_content_ref"] == expected["source_content_ref"]')
audit = audit.replace('helper = FROZEN / "strip_binaries.py"', '''assert provenance["source_revision_by_variant"] == {
    name: value["source_content_ref"] for name, value in INPUTS["expected_variants"].items()
}
prior = ROOT.parent / "host2"
assert INPUTS["preceding_cohort_manifest_sha256"] == sha(prior / "frozen/manifest.json")
assert INPUTS["preceding_driver_sha256"] == sha(prior / "frozen/build_driver_host2_pr175_sbom.py")
assert provenance["preserved_artifact_sha256"]["host2-pr175-sbom-inputs.json"] == INPUTS["preceding_cohort_manifest_sha256"]
assert provenance["preserved_artifact_sha256"]["build_driver_host2_pr175_sbom.py"] == INPUTS["preceding_driver_sha256"]
assert provenance["preserved_artifact_sha256"]["provenance-host2-pr175-sbom.json"] == sha(prior / "results/provenance.json")
assert provenance["preceding_manifest_records"] == {
    f"cargo-{variant}": json.loads((prior / "results" / f"cargo-{variant}.build.json").read_text())
    for variant in ("pr175", "pr175-lazy-sbom")
}
helper = FROZEN / "strip_binaries.py"''')
audit = audit.replace('prior_baseline = ROOT.parent / "results/cargo-pr175"\n', '')
start = audit.index('    "host2_baseline_sha256":')
end = audit.index('    "records": records,', start)
audit = audit[:start] + audit[end:]
audit = audit.replace('"audit-pair.json" if len(variants) == 2', '"audit-cohort.json" if len(variants) == 3')
ast.parse(audit)
files["audit.py"] = audit.encode()

reference = (ROOT / "host2/frozen/reference-host7-provenance.json").read_bytes()
helper = (ROOT / "host2/frozen/strip_binaries.py").read_bytes()
assert sha(reference) == old_inputs["reference_host7_provenance_sha256"]
assert sha(helper) == old_inputs["strip_helper_sha256"]
files["reference-host7-provenance.json"] = reference
files["strip_binaries.py"] = helper
manifest = {
    "cohort": "host2-current-stack",
    "variant_order": list(ORDER),
    "driver_sha256": sha(driver.encode()),
    "strip_helper_sha256": sha(helper),
    "source_bundle_sha256": old_inputs["source_bundle_sha256"],
    "patch_sha256": HASHES,
    "expected_variants": expected,
    "initial_source_tree": INITIAL_TREE,
    "reference_host7_provenance_sha256": sha(reference),
    "preceding_cohort_manifest_sha256": sha((ROOT / "host2/frozen/manifest.json").read_bytes()),
    "preceding_driver_sha256": old_inputs["driver_sha256"],
    "incremental_path_patch_sha256": INCREMENTAL_HASH,
    "canonical_diff_format": "git diff --cached --binary --full-index --no-ext-diff --no-textconv <pinned>",
}
files["manifest.json"] = (json.dumps(manifest, indent=2) + "\n").encode()
files["verification-scripts.json"] = (json.dumps({
    name: sha(files[name]) for name in ("collect_variant.py", "audit.py")
}, indent=2) + "\n").encode()
files[Path(__file__).name] = Path(__file__).read_bytes()
COHORT.mkdir()
(COHORT / "frozen").mkdir()
(COHORT / "results").mkdir()
for filename, data in files.items():
    with (COHORT / "frozen" / filename).open("xb") as stream:
        stream.write(data)
    if filename in ("build_driver_host2_current_stack.py", "collect_variant.py", "audit.py"):
        with (COHORT / filename).open("xb") as stream:
            stream.write(data)
print(json.dumps(manifest, indent=2))
