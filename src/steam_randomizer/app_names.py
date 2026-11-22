"""App names from Steam's local caches. Offline, stdlib only.

Supports:
  * appcache/appinfo.vdf — v39/40/41 (magic 0x07564427..29)
  * appcache/appinfo/appinfo_XX.vdf — v42, 256 shards (Steam client ≥ Nov 2026)
  * Registry fallback: HKCU\\Software\\Valve\\Steam\\Apps\\<id>\\Name
"""
from __future__ import annotations

import struct
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

_MAGIC_BASE = 0x075644
_END = (0x08, 0x0B)


@dataclass(frozen=True)
class AppInfo:
    appid: str
    name: str
    type: str = ""      # game / dlc / tool / music / application / demo ...
    parent: str = ""


# ---- low-level binary VDF helpers ------------------------------------

def _cstr(buf: bytes, pos: int) -> tuple[str, int]:
    end = buf.index(b"\x00", pos)
    return buf[pos:end].decode("utf-8", "replace"), end + 1


def _string_table(buf: bytes, pos: int, count: int) -> list[str]:
    out = []
    for _ in range(count):
        s, pos = _cstr(buf, pos)
        out.append(s)
    return out


def _read_key(buf: bytes, pos: int, strings: list[str] | None) -> tuple[str, int]:
    if strings is None:
        return _cstr(buf, pos)
    (idx,) = struct.unpack_from("<i", buf, pos)
    pos += 4
    if idx < 0:
        return strings[-idx - 1], pos
    return _cstr(buf, pos)


def _read_value(buf: bytes, pos: int, strings: list[str] | None, kind: int):
    if kind == 0x00:  # nested object
        return _read_dict(buf, pos, strings)[0], pos
    if kind == 0x01:  # string
        return _cstr(buf, pos)
    if kind == 0x02:  # int32
        (v,) = struct.unpack_from("<i", buf, pos)
        return v, pos + 4
    if kind == 0x03:  # float32
        (v,) = struct.unpack_from("<f", buf, pos)
        return v, pos + 4
    if kind == 0x05:  # wide string
        end = pos
        while buf[end:end + 2] != b"\x00\x00":
            end += 2
        return buf[pos:end].decode("utf-16-le", "replace"), end + 2
    if kind == 0x07:  # uint64
        (v,) = struct.unpack_from("<Q", buf, pos)
        return v, pos + 8
    if kind == 0x0A:  # int64
        (v,) = struct.unpack_from("<q", buf, pos)
        return v, pos + 8
    # Unknown — bail out gracefully.
    raise ValueError(f"unknown type 0x{kind:02x}")


def _read_dict(buf: bytes, pos: int, strings: list[str] | None) -> tuple[dict, int]:
    out: dict = {}
    while pos < len(buf):
        kind = buf[pos]
        pos += 1
        if kind in _END:
            return out, pos
        key, pos = _read_key(buf, pos, strings)
        try:
            out[key], pos = _read_value(buf, pos, strings, kind)
        except (ValueError, IndexError, struct.error):
            return out, len(buf)
    return out, pos


def _read_root(buf: bytes, pos: int, strings: list[str] | None) -> dict:
    kind = buf[pos]
    pos += 1
    if kind in _END:
        return {}
    key, pos = _read_key(buf, pos, strings)
    value, _ = _read_value(buf, pos, strings, kind)
    return {key: value}


# ---- version detection ------------------------------------------------

def _version(buf: bytes) -> int:
    (magic,) = struct.unpack_from("<I", buf, 0)
    if magic >> 8 != _MAGIC_BASE:
        raise ValueError(f"not an appinfo.vdf: magic=0x{magic:08x}")
    return magic & 0xFF


# ---- v39 / v40 / v41 (legacy single file) ----------------------------

def _iter_legacy(buf: bytes):
    version = _version(buf)
    pos = 8
    strings = None

    if version >= 41:
        (table_offset,) = struct.unpack_from("<Q", buf, pos)
        pos += 8
        (string_count,) = struct.unpack_from("<I", buf, table_offset)
        strings = _string_table(buf, table_offset + 4, string_count)

    pos += 4 if version < 41 else 0
    section_size = 44 if version >= 40 else (8 if version >= 39 else 0)
    if section_size == 44:
        pos += 4 + 4 + 8 + 20 + 4  # infoState/lastUpdated/token/sha1/changeNumber

    while pos + 8 <= len(buf):
        appid, size = struct.unpack_from("<II", buf, pos)
        pos += 8
        if appid == 0 or size == 0:
            break
        data_start = pos + section_size
        yield appid, data_start, strings
        pos = data_start + (size - section_size)


# ---- v42 (256 shards) -------------------------------------------------

def _iter_shard(buf: bytes):
    (_shard, _count, app_count, index_size,
     string_count, string_table_size, _data_size, _crc1, _crc2) = struct.unpack_from("<9I", buf, 8)

    index_pos = 44
    st_pos = index_pos + index_size
    data_pos = st_pos + string_table_size
    strings = _string_table(buf, st_pos, string_count)

    pos = index_pos
    for _ in range(app_count):
        appid, data_offset, _data_size, summary_size = struct.unpack_from("<4I", buf, pos)
        yield appid, data_pos + data_offset + 20, strings
        pos += 16 + summary_size


# ---- files & registry -------------------------------------------------

def _cache_files(steam_path: Path) -> list[Path]:
    files = []
    legacy = steam_path / "appcache" / "appinfo.vdf"
    if legacy.is_file():
        files.append(legacy)
    shard_dir = steam_path / "appcache" / "appinfo"
    if shard_dir.is_dir():
        files.extend(sorted(shard_dir.glob("appinfo_*.vdf")))
    return files


def read_appinfo(steam_path: Path, appids: Iterable[str] | None = None) -> dict[str, AppInfo]:
    wanted = {str(a) for a in appids} if appids is not None else None
    result: dict[str, AppInfo] = {}

    for path in _cache_files(steam_path):
        try:
            buf = path.read_bytes()
            version = _version(buf)
            entries = _iter_shard(buf) if version >= 42 else _iter_legacy(buf)

            for appid, pos, strings in entries:
                key = str(appid)
                if wanted is not None and key not in wanted:
                    continue
                try:
                    common = _read_root(buf, pos, strings).get("appinfo", {}).get("common", {})
                except (ValueError, IndexError, struct.error):
                    continue
                name = common.get("name")
                if isinstance(name, str) and name:
                    result[key] = AppInfo(
                        key, name,
                        str(common.get("type", "")).lower(),
                        str(common.get("parent", "")),
                    )
        except (OSError, ValueError, IndexError, struct.error):
            continue

    return result


def read_registry_names() -> dict[str, str]:
    """HKCU\\Software\\Valve\\Steam\\Apps\\<id>\\Name — Windows only."""
    try:
        import winreg
    except ImportError:
        return {}

    names: dict[str, str] = {}
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam\Apps") as root:
            i = 0
            while True:
                try:
                    appid = winreg.EnumKey(root, i)
                except OSError:
                    break
                i += 1
                if not appid.isdigit():
                    continue
                try:
                    with winreg.OpenKey(root, appid) as sub:
                        value, _ = winreg.QueryValueEx(sub, "Name")
                except OSError:
                    continue
                if isinstance(value, str) and value.strip():
                    names[appid] = value.strip()
    except OSError:
        return {}

    return names


def resolve_names(steam_path: Path, appids: Iterable[str]) -> dict[str, AppInfo]:
    """appid -> AppInfo: appinfo.vdf, registry, then Steam Store API."""
    wanted = {str(a) for a in appids}

    # 1. Local appinfo cache (has type info)
    found = read_appinfo(steam_path, wanted)

    # 2. Registry fallback
    missing = wanted - found.keys()
    if missing:
        for appid, name in read_registry_names().items():
            if appid in missing:
                found[appid] = AppInfo(appid, name)

    # 3. Steam Store API for the rest
    missing = wanted - found.keys()
    if missing:
        from .steam_api import get_app_details
        names = get_app_details(list(missing))
        for appid, name in names.items():
            found[appid] = AppInfo(appid, name)

    return found