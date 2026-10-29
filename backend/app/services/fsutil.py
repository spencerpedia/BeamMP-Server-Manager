"""File copying with progress reporting, for imports and templates that can be gigabytes of mods."""

import os
import shutil
from collections.abc import Callable, Iterable
from pathlib import Path


def tree_size(paths: Iterable[Path]) -> int:
    total = 0
    for root in paths:
        if root.is_file():
            total += root.stat().st_size
        elif root.is_dir():
            for f in root.rglob("*"):
                if f.is_file():
                    total += f.stat().st_size
    return total


class Copier:
    """Copies files and directories while reporting overall progress via on_progress(fraction, done, total)."""

    def __init__(self, total: int, on_progress: Callable[[float, int, int], None] | None = None):
        self.total = max(total, 1)
        self.done = 0
        self.on_progress = on_progress

    def _report(self) -> None:
        if self.on_progress:
            self.on_progress(min(self.done / self.total, 1.0), self.done, self.total)

    def file(self, src: Path, dst: Path) -> None:
        dst.parent.mkdir(parents=True, exist_ok=True)
        # Mod zips are never modified in place (uploads, installs and toggles all replace/rename), so
        # sharing them via hard links between servers and templates is safe and saves gigabytes.
        if src.suffix.lower() == ".zip":
            try:
                dst.unlink(missing_ok=True)
                os.link(src, dst)
                self.done += src.stat().st_size
                self._report()
                return
            except OSError:
                pass  # different filesystem or read-only source: fall back to copying
        with src.open("rb") as fin, dst.open("wb") as fout:
            while chunk := fin.read(4 << 20):
                fout.write(chunk)
                self.done += len(chunk)
                self._report()
        shutil.copystat(src, dst, follow_symlinks=False)

    def tree(self, src: Path, dst: Path, skip: Callable[[Path], bool] = lambda p: False) -> None:
        for dirpath, dirnames, filenames in os.walk(src):
            here = Path(dirpath)
            dirnames[:] = [d for d in dirnames if not skip(here / d)]
            for name in filenames:
                f = here / name
                if not skip(f):
                    self.file(f, dst / f.relative_to(src))
