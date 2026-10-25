#!/usr/bin/env python3
"""Default: read-only verification of the customized XI opening.

--record explicitly records reviewed local source hashes.
--import-upstream NEW_DIRECTORY exports reference sources to a NEW directory only;
it never overwrites this project's working files.
"""
import argparse
import re
import shutil
from hashlib import sha256
from pathlib import Path

HERE = Path(__file__).resolve().parent
UPSTREAM = HERE.parent / "RhineLabUI"
MANIFEST = HERE / "源码校验.sha256"
REFERENCE = [
    "boot.ts", "boot-motion.ts", "boot-tracks.ts", "boot-orbit-tracks.ts",
    "boot-logo-tracks.ts", "boot-lettering.ts", "boot-lettering-art.json",
    "boot-lettering.css", "brand.ts", "style.css", "responsive.css",
]


def source_files():
    return sorted(p for root in (HERE / "src", HERE.parent / "shared")
                  for p in root.iterdir() if p.is_file())


def relative(path):
    import os
    return os.path.relpath(path, HERE)


def record():
    MANIFEST.write_text("".join(f"{sha256(p.read_bytes()).hexdigest()}  {relative(p)}\n" for p in source_files()))
    print("Recorded reviewed local sources, including shared playback and tilt.")


def verify():
    errors = []
    listed = set()
    for line in MANIFEST.read_text().splitlines():
        digest, name = line.split(None, 1)
        p = (HERE / name).resolve()
        listed.add(p)
        if not p.is_file() or sha256(p.read_bytes()).hexdigest() != digest:
            errors.append(f"Source changed or missing: {name}")
    for p in source_files():
        if p.resolve() not in listed:
            errors.append(f"Unrecorded source: {relative(p)}")
        if p.suffix != ".ts":
            continue
        for target in re.findall(r'(?:from\s+|import\s*)[\"\'](\.[^\"\']+)[\"\']', p.read_text()):
            candidate = p.parent / target
            if not any(Path(str(candidate) + suffix).is_file() for suffix in ("", ".ts", ".d.ts", ".js", ".css", ".json")):
                errors.append(f"Missing import: {relative(p)} → {target}")
    if errors:
        print("\n".join(errors))
        return 1
    print(f"Verified {len(listed)} source hashes and relative imports. No files written.")
    return 0


def import_reference(destination):
    output = Path(destination).resolve()
    if output.exists():
        raise SystemExit("Refusing to overwrite an existing directory. Choose a new reference directory.")
    files = [UPSTREAM / "src" / name for name in REFERENCE]
    if any(not p.is_file() for p in files):
        raise SystemExit("Reference source files are missing.")
    output.mkdir(parents=True)
    for source in files:
        shutil.copy2(source, output / source.name)
    print(f"Reference snapshot exported to {output}; the XI working tree was not changed.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--record", action="store_true")
    group.add_argument("--import-upstream", metavar="NEW_DIRECTORY")
    args = parser.parse_args()
    if args.record:
        record()
    elif args.import_upstream:
        import_reference(args.import_upstream)
    else:
        raise SystemExit(verify())
