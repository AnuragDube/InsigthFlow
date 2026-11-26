"""Back up a stopped InsightFlow SQLite workspace and restore it to a fresh directory."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sqlite3
from collections.abc import Iterator
from contextlib import closing, contextmanager
from pathlib import Path

from sqlalchemy.engine import make_url

from insightflow.core.settings import get_settings

DATABASE = "metadata.sqlite3"
MANIFEST = "manifest.json"


def _files(root: Path, excluded: frozenset[Path] = frozenset()) -> Iterator[Path]:
    for child in sorted(root.iterdir()):
        if child in excluded:
            continue
        if child.is_symlink() or child.is_junction():
            raise ValueError("Workspace backups require ordinary files and directories.")
        if child.is_dir():
            yield from _files(child, excluded)
        elif child.is_file():
            yield child
        else:
            raise ValueError("Workspace backups require ordinary files and directories.")


def _inventory(root: Path) -> dict[str, str]:
    result = {}
    for path in _files(root, frozenset({root / MANIFEST})):
        with path.open("rb") as file:
            result[path.relative_to(root).as_posix()] = hashlib.file_digest(
                file, "sha256"
            ).hexdigest()
    return result


@contextmanager
def _new_directory(path: Path) -> Iterator[Path]:
    path.mkdir(mode=0o700, exist_ok=False)
    try:
        yield path
    except BaseException:
        shutil.rmtree(path)
        raise


def _verify_database(path: Path) -> None:
    with closing(sqlite3.connect(f"{path.as_uri()}?mode=ro", uri=True)) as connection:
        if connection.execute("PRAGMA quick_check").fetchall() != [("ok",)]:
            raise ValueError("SQLite integrity check failed.")
        if connection.execute("PRAGMA foreign_key_check").fetchone() is not None:
            raise ValueError("SQLite foreign key check failed.")
        if connection.execute("SELECT version_num FROM alembic_version").fetchone() is None:
            raise ValueError("The database has no InsightFlow schema version.")


def backup(destination: Path) -> None:
    settings = get_settings()
    config = make_url(settings.database_url)
    if config.get_backend_name() != "sqlite" or not config.database or config.query:
        raise ValueError("Backup requires a file-backed SQLite database URL without query options.")
    database = Path(config.database).resolve(strict=True)
    data = settings.data_dir.resolve(strict=True)
    if not database.is_file() or not data.is_dir() or destination.is_relative_to(data):
        raise ValueError("Choose a new backup directory outside the application data directory.")
    excluded = frozenset(
        {database, *(database.with_name(database.name + s) for s in ("-wal", "-shm", "-journal"))}
    )
    with _new_directory(destination):
        warehouse = destination / "data"
        warehouse.mkdir()
        with (
            closing(sqlite3.connect(f"{database.as_uri()}?mode=ro", uri=True)) as source,
            closing(sqlite3.connect(destination / DATABASE)) as target,
        ):
            source.backup(target)
            target.execute("PRAGMA journal_mode=DELETE")
            if target.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='browser_sessions'"
            ).fetchone():
                # Restoring a workspace should never revive a formerly valid login.
                target.execute("DELETE FROM browser_sessions")
                target.commit()
        _verify_database(destination / DATABASE)
        for path in _files(data, excluded):
            copy = warehouse / path.relative_to(data)
            copy.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, copy)
        (destination / MANIFEST).write_text(
            json.dumps({"version": 1, "sha256": _inventory(destination)}, indent=2),
            encoding="utf-8",
        )


def restore(snapshot: Path, destination: Path) -> None:
    manifest = snapshot / MANIFEST
    if manifest.is_symlink() or destination.is_relative_to(snapshot):
        raise ValueError("Choose a new restore directory outside the backup directory.")
    expected = json.loads(manifest.read_text(encoding="utf-8"))
    if (
        not isinstance(expected, dict)
        or expected.get("version") != 1
        or expected.get("sha256") != _inventory(snapshot)
    ):
        raise ValueError("Workspace backup failed checksum verification.")
    if not (snapshot / DATABASE).is_file() or not (snapshot / "data").is_dir():
        raise ValueError("Workspace backup is incomplete.")
    with _new_directory(destination):
        shutil.copyfile(snapshot / DATABASE, destination / DATABASE)
        shutil.copytree(snapshot / "data", destination / "data")
        if _inventory(destination) != expected["sha256"]:
            raise ValueError("Restored files failed checksum verification.")
        _verify_database(destination / DATABASE)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("backup").add_argument("destination", type=Path)
    restore_parser = sub.add_parser("restore")
    restore_parser.add_argument("snapshot", type=Path)
    restore_parser.add_argument("destination", type=Path)
    args = parser.parse_args()
    try:
        destination = args.destination.resolve()
        if args.command == "backup":
            backup(destination)
        else:
            restore(args.snapshot.resolve(strict=True), destination)
    except (OSError, ValueError, sqlite3.Error) as exc:
        parser.exit(1, f"Workspace {args.command} failed: {exc}\n")
    print(f"Workspace {args.command} complete: {destination}")


if __name__ == "__main__":
    main()
