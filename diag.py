"""Diagnostic for full-library feature (app_names version)."""
from __future__ import annotations

from steam_randomizer.steam_locator import find_steam_path


def show_localconfig(steam_path):
    from steam_randomizer.full_library import _find_latest_userdata, _load_owned_appids

    print("\n--- localconfig.vdf ---")
    config_dir = _find_latest_userdata(steam_path)
    print(f"config dir: {config_dir}")

    owned = _load_owned_appids(config_dir)
    print(f"[{'OK' if owned else 'FAIL'}] owned appids: {len(owned)}")
    if owned:
        print(f"  sample: {sorted(owned)[:5]}")
    return owned


def show_appinfo(steam_path, sample_appids):
    from steam_randomizer.app_names import read_appinfo, read_registry_names

    print("\n--- appinfo (local cache) ---")
    infos = read_appinfo(steam_path)
    print(f"[{'OK' if infos else 'INFO'}] appinfo entries: {len(infos)}")

    reg = read_registry_names()
    print(f"[{'OK' if reg else 'INFO'}] registry names: {len(reg)}")


def show_steam_api(sample_appids):
    from steam_randomizer.steam_api import _cache_path, get_app_details

    print("\n--- Steam Store API ---")
    path = _cache_path()
    if path:
        print(f"  cache: {path}")
        print(f"  exists: {path.is_file()}")

    names = get_app_details(list(sample_appids))
    print(f"[{'OK' if names else 'FAIL'}] names fetched: {len(names)} / {len(sample_appids)}")
    if names:
        sample_id = next(iter(names))
        print(f"  sample: {sample_id} -> {names[sample_id]}")


def main():
    steam = find_steam_path()
    print(f"Steam path: {steam}")
    owned = show_localconfig(steam)
    if owned:
        sample = sorted(owned)[:10]  # первые 10 для теста
        show_appinfo(steam, sample)
        show_steam_api(sample)

        from steam_randomizer.app_names import resolve_names
        resolved = resolve_names(steam, owned)
        print(f"\n--- resolve_names ---")
        print(f"  resolved: {len(resolved)} / {len(owned)}")


if __name__ == "__main__":
    main()