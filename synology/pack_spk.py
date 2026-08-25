#!/usr/bin/env python3
"""Create and validate a DSM SPK with deterministic Unix metadata."""

from __future__ import annotations

import argparse
import gzip
import io
from pathlib import Path, PurePosixPath
import tarfile


TEXT_SUFFIXES = {".css", ".html", ".js", ".json", ".mjs", ".py"}


def normalized_bytes(path: Path, relative: str, outer: bool) -> bytes:
    data = path.read_bytes()
    rel = PurePosixPath(relative)
    is_text = (
        (outer and (relative == "INFO" or rel.parts[0] in {"conf", "scripts"}))
        or (
            not outer
            and (
                rel.suffix in TEXT_SUFFIXES
                or relative == "ui/config"
                or rel.parts[:2] == ("ui", "texts")
            )
        )
    )
    return data.replace(b"\r\n", b"\n").replace(b"\r", b"\n") if is_text else data


def add_tree(archive: tarfile.TarFile, root: Path, outer: bool) -> None:
    for path in sorted(root.rglob("*"), key=lambda item: item.as_posix()):
        relative = path.relative_to(root).as_posix()
        info = archive.gettarinfo(str(path), arcname=relative)
        info.uid = 0
        info.gid = 0
        info.uname = "root"
        info.gname = "root"
        info.mtime = 0
        if path.is_dir():
            info.mode = 0o755
            archive.addfile(info)
            continue
        executable = (outer and relative.startswith("scripts/")) or (not outer and relative == "bin/node")
        info.mode = 0o755 if executable else 0o644
        data = normalized_bytes(path, relative, outer)
        info.size = len(data)
        archive.addfile(info, io.BytesIO(data))


def safe_members(archive: tarfile.TarFile) -> dict[str, tarfile.TarInfo]:
    members = {member.name.rstrip("/"): member for member in archive.getmembers()}
    for name in members:
        path = PurePosixPath(name)
        if path.is_absolute() or ".." in path.parts:
            raise RuntimeError(f"Unsafe archive path: {name}")
    return members


def validate(spk_path: Path, expected_version: str) -> None:
    with tarfile.open(spk_path, "r:") as outer:
        members = safe_members(outer)
        required = {"INFO", "package.tgz", "conf/privilege", "conf/resource"}
        required.update(f"scripts/{name}" for name in (
            "postinst", "postuninst", "postupgrade", "preinst", "preuninst", "preupgrade", "start-stop-status"
        ))
        missing = sorted(required - members.keys())
        if missing:
            raise RuntimeError("SPK is missing: " + ", ".join(missing))
        info_data = outer.extractfile(members["INFO"]).read()
        if b"\r" in info_data or f'version="{expected_version}"'.encode() not in info_data:
            raise RuntimeError("INFO has invalid line endings or version")
        for name in sorted(required):
            if not name.startswith("scripts/"):
                continue
            member = members[name]
            data = outer.extractfile(member).read()
            if b"\r" in data or not data.startswith(b"#!/bin/sh\n"):
                raise RuntimeError(f"{name} is not a Unix shell script")
            if member.mode & 0o111 == 0:
                raise RuntimeError(f"{name} is not executable")
        package_data = outer.extractfile(members["package.tgz"]).read()

    with tarfile.open(fileobj=io.BytesIO(package_data), mode="r:gz") as inner:
        members = safe_members(inner)
        for name in ("backend.py", "bin/node", "gofile_wt.mjs", "web/index.html"):
            if name not in members:
                raise RuntimeError(f"package.tgz is missing: {name}")
        if members["bin/node"].mode & 0o111 == 0:
            raise RuntimeError("Bundled Node.js runtime is not executable")
        for name in ("backend.py", "gofile_wt.mjs", "web/index.html"):
            if b"\r" in inner.extractfile(members[name]).read():
                raise RuntimeError(f"{name} has non-Unix line endings")


def build(inner_root: Path, outer_root: Path, output: Path, version: str) -> None:
    package_tgz = outer_root / "package.tgz"
    with package_tgz.open("wb") as raw:
        with gzip.GzipFile(fileobj=raw, mode="wb", mtime=0) as compressed:
            with tarfile.open(fileobj=compressed, mode="w", format=tarfile.PAX_FORMAT) as archive:
                add_tree(archive, inner_root, outer=False)
    output.parent.mkdir(parents=True, exist_ok=True)
    with tarfile.open(output, "w", format=tarfile.PAX_FORMAT) as archive:
        add_tree(archive, outer_root, outer=True)
    validate(output, version)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--inner", type=Path, required=True)
    parser.add_argument("--outer", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--version", required=True)
    args = parser.parse_args()
    build(args.inner.resolve(), args.outer.resolve(), args.output.resolve(), args.version)
    print(args.output.resolve())


if __name__ == "__main__":
    main()
