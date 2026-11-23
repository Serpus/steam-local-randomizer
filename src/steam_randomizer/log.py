"""Единый логгер: файл (виден даже в --windowed exe) + stderr.

Файл: <config_dir>/logs/app.log (ротация 1MB x3).
Без env-переменных пишем INFO+ в файл (причины missing/битых иконок видны
сразу). С STEAM_RANDOMIZER_DEBUG / _DEBUG_ICONS / _DEBUG_API — полный DEBUG.
"""
from __future__ import annotations

import logging
import os
import sys
from logging.handlers import RotatingFileHandler

from .settings import config_dir

_NAME = "steam_randomizer"
_configured = False


def get_logger() -> logging.Logger:
    global _configured
    logger = logging.getLogger(_NAME)
    if _configured:
        return logger
    _configured = True

    verbose = any(
        os.environ.get(v)
        for v in ("STEAM_RANDOMIZER_DEBUG", "STEAM_RANDOMIZER_DEBUG_ICONS", "STEAM_RANDOMIZER_DEBUG_API")
    )
    logger.setLevel(logging.DEBUG if verbose else logging.INFO)
    logger.propagate = False
    fmt = logging.Formatter("%(asctime)s %(levelname)-7s %(message)s", "%H:%M:%S")

    sh = logging.StreamHandler(sys.stderr)
    sh.setFormatter(fmt)
    sh.setLevel(logging.DEBUG if verbose else logging.WARNING)
    logger.addHandler(sh)

    base = config_dir()
    if base is not None:
        try:
            logdir = base / "logs"
            logdir.mkdir(parents=True, exist_ok=True)
            path = logdir / "app.log"
            fh = RotatingFileHandler(path, maxBytes=1_000_000, backupCount=3, encoding="utf-8")
            fh.setFormatter(fmt)
            fh.setLevel(logging.DEBUG if verbose else logging.INFO)
            logger.addHandler(fh)
            print(f"[steam-randomizer] log: {path}", file=sys.stderr)
            logger.info("=== log started (verbose=%s) ===", verbose)
        except OSError:
            pass
    return logger