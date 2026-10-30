#!/usr/bin/env python3
"""Verify the published C/CZD package result with Python 3.11+ and no SDK."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import tempfile
import zipfile


ZIP_SHA256 = "cdd67c8caa1924d569577f989994c0f9612bc206ff040524dfc42a286ab3d5ff"
OUTER_SHA256 = "edfac39132b05b2b6754e7b2c5db25d52b6a041d4985c3b7a27f79596d92e05c"


def checked_extract(packet, dest):
    with packet.open("rb") as stream:
        def verify_digest():
            stream.seek(0)
            if hashlib.file_digest(stream, "sha256").hexdigest() != ZIP_SHA256:
                raise ValueError("unexpected combined packet SHA-256")
        verify_digest()
        stream.seek(0)
        with zipfile.ZipFile(stream) as archive:
            members = archive.infolist()
            if len(members) != 567 or sum(entry.file_size for entry in members) != 29_559_452:
                raise ValueError("unexpected combined packet inventory")
            for entry in members:
                name = entry.filename
                if (stat.S_IFMT(entry.external_attr >> 16) != stat.S_IFREG or
                    "\\" in name or ":" in name or any(p in ("", ".", "..") for p in name.split("/"))):
                    raise ValueError(f"invalid packet member {name!r}")
                path = dest / name
                path.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(entry) as src, path.open("xb") as out:
                    shutil.copyfileobj(src, out)
        verify_digest()


def replay(packet):
    with tempfile.TemporaryDirectory(prefix="ohm-uv-package-") as temp:
        root = Path(temp)
        extracted = root / "packet"
        scratch = root / "standalone" / "scratch"
        scratch.mkdir(parents=True)
        checked_extract(packet, extracted)
        process = subprocess.run(
            [sys.executable, "-ISB", str(extracted / "verify.py"),
             "--expected-outer", OUTER_SHA256, "--scratch", str(scratch)],
            cwd=extracted, stdout=subprocess.PIPE, check=True,
        )
        verified = json.loads(process.stdout)
    result = verified["outcomes"]["combined"]["result"]
    score = result["score"]
    return {
        "comparison": "C to CZD, ordinary first-edited full package test build",
        "packet_sha256": ZIP_SHA256,
        "native_outer_sha256": OUTER_SHA256,
        "pairs": score["pairs"],
        "median_seconds": {"C": score["C_seconds_median"], "CZD": score["candidate_seconds_median"]},
        "median_paired_speedup": score["ratio_median"],
        "median_paired_seconds_saved": score["paired_seconds_saved_median"],
        "paired_speedup_interval": score["rank_3_to_10"],
        "interval_coverage": score["exact_median_interval_coverage"],
        "twofold_sign_test": score["p_against_2"],
        "twofold_gate_passed": score["individual_gate"],
        "holm10": verified["holm10"]["CZD/package-test-v3"],
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("packet", type=Path, help="downloaded package-test-v3-combined.zip")
    try:
        print(json.dumps(replay(parser.parse_args().packet), indent=2))
    except (OSError, ValueError, zipfile.BadZipFile, subprocess.CalledProcessError) as error:
        parser.exit(1, f"Replay failed: {error}\n")
