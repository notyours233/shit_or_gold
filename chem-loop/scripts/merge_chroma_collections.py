#!/usr/bin/env python3
"""Merge reaction Chroma collections into the main literature persist directory.

This keeps collection names unchanged. The merged directory therefore contains:
- material_property_literature_agent1..4
- electrochemistry_literature_agent1..4

Runtime task isolation remains metadata-based (reaction_type/task family filters).
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path
from typing import Iterable

import chromadb
from chromadb.config import Settings


def _client(path: Path):
    os.environ.setdefault("SQLITE_TMPDIR", "/tmp")
    os.environ.setdefault("TMPDIR", "/tmp")
    return chromadb.PersistentClient(
        path=str(path.resolve()),
        settings=Settings(anonymized_telemetry=False, allow_reset=False),
    )


def _collection_names(client) -> set[str]:
    collections = client.list_collections()
    names: set[str] = set()
    for item in collections:
        names.add(getattr(item, "name", str(item)))
    return names


def _chunks(total: int, batch_size: int) -> Iterable[tuple[int, int]]:
    for offset in range(0, total, batch_size):
        yield offset, min(batch_size, total - offset)


def copy_collection(src_client, dst_client, name: str, batch_size: int) -> None:
    src = src_client.get_collection(name)
    total = int(src.count())

    if name in _collection_names(dst_client):
        dst_existing = dst_client.get_collection(name)
        existing_count = int(dst_existing.count())
        if existing_count == total:
            print(f"[skip] {name}: already present with {existing_count} rows")
            return
        raise RuntimeError(
            f"destination collection {name!r} already exists with {existing_count} rows; "
            f"source has {total}. Refusing to overwrite automatically."
        )

    dst = dst_client.get_or_create_collection(
        name=name,
        metadata=dict(getattr(src, "metadata", None) or {"hnsw:space": "cosine"}),
    )

    copied = 0
    for offset, limit in _chunks(total, batch_size):
        batch = src.get(
            limit=limit,
            offset=offset,
            include=["documents", "embeddings", "metadatas"],
        )
        ids = batch.get("ids") or []
        documents = batch.get("documents") or []
        metadatas = batch.get("metadatas") or []
        embeddings = batch.get("embeddings")
        if hasattr(embeddings, "tolist"):
            embeddings = embeddings.tolist()

        if not ids:
            continue
        dst.add(
            ids=list(ids),
            documents=list(documents),
            metadatas=list(metadatas),
            embeddings=embeddings,
        )
        copied += len(ids)
        print(f"[copy] {name}: {copied}/{total}", flush=True)

    final_count = int(dst.count())
    if final_count != total:
        raise RuntimeError(f"{name}: copied {final_count}, expected {total}")
    print(f"[done] {name}: {final_count} rows")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", default="MAD/data/chroma_db2", help="source Chroma persist directory")
    parser.add_argument("--dest", default="MAD/data/chroma_db", help="destination Chroma persist directory")
    parser.add_argument("--batch-size", type=int, default=2000)
    parser.add_argument(
        "--collection-prefix",
        default="electrochemistry_literature_agent",
        help="copy collections whose names start with this prefix",
    )
    args = parser.parse_args()

    source = Path(args.source)
    dest = Path(args.dest)
    if not (source / "chroma.sqlite3").exists():
        raise FileNotFoundError(f"source Chroma DB not found: {source / 'chroma.sqlite3'}")
    if not (dest / "chroma.sqlite3").exists():
        raise FileNotFoundError(f"destination Chroma DB not found: {dest / 'chroma.sqlite3'}")

    src_client = _client(source)
    dst_client = _client(dest)
    names = sorted(n for n in _collection_names(src_client) if n.startswith(args.collection_prefix))
    if not names:
        raise RuntimeError(f"no collections matching prefix {args.collection_prefix!r} in {source}")

    print(f"source={source.resolve()}")
    print(f"dest={dest.resolve()}")
    print("collections=" + ", ".join(names))
    for name in names:
        copy_collection(src_client, dst_client, name, batch_size=max(1, int(args.batch_size)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
