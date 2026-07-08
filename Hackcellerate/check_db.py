"""Quick ChromaDB inspection tool.

Usage (from project root, with .venv active):
    python check_db.py                      # summary
    python check_db.py --sample 5           # show 5 random chunks
    python check_db.py --search "diabetes"  # semantic search
    python check_db.py --by-source          # count per source
    python check_db.py --doc-ids            # unique doc ids + titles
"""
from __future__ import annotations

import argparse
from collections import Counter

from app.config import get_settings
from app.core.embeddings import get_embedding_model
from app.core.vector_store import get_vector_store


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--sample", type=int, default=0, help="Show N random chunks (via peek).")
    p.add_argument("--search", type=str, default=None, help="Semantic search for this text; show top matches.")
    p.add_argument("--top-k", type=int, default=5)
    p.add_argument("--by-source", action="store_true", help="Count chunks per 'source' metadata value.")
    p.add_argument("--doc-ids", action="store_true", help="List unique doc_id + title.")
    args = p.parse_args()

    s = get_settings()
    store = get_vector_store()
    col = store.collection

    print(f"Chroma dir       : {s.chroma_dir}")
    print(f"Collection       : {s.chroma_collection}")
    print(f"Total chunks     : {col.count()}")

    if args.sample:
        peek = col.peek(limit=args.sample)
        print(f"\n--- first {args.sample} chunks ---")
        for i, (cid, doc, meta) in enumerate(zip(peek["ids"], peek["documents"], peek["metadatas"])):
            print(f"\n[{i+1}] id={cid}")
            print(f"    source={meta.get('source')}  doc_type={meta.get('doc_type')}  title={meta.get('title')}")
            print(f"    text  : {(doc or '')[:200].replace(chr(10),' ')} ...")

    if args.by_source:
        all_meta = col.get(include=["metadatas"]).get("metadatas") or []
        counts = Counter((m or {}).get("source", "unknown") for m in all_meta)
        print("\n--- chunks per source ---")
        for src, n in counts.most_common():
            print(f"  {n:>7}  {src}")

    if args.doc_ids:
        all_meta = col.get(include=["metadatas"]).get("metadatas") or []
        docs: dict[str, str] = {}
        for m in all_meta:
            if not m:
                continue
            did = m.get("doc_id")
            if did and did not in docs:
                docs[did] = m.get("title", "")
        print(f"\n--- {len(docs)} unique documents ---")
        for did, title in list(docs.items())[:50]:
            print(f"  {did}  {title}")
        if len(docs) > 50:
            print(f"  ... and {len(docs) - 50} more")

    if args.search:
        embedder = get_embedding_model()
        q_vec = embedder.embed_one(args.search)
        res = store.query(query_embedding=q_vec, top_k=args.top_k)
        print(f"\n--- top {args.top_k} matches for: {args.search!r} ---")
        for i, (cid, doc, meta, dist) in enumerate(
            zip(res["ids"], res["documents"], res["metadatas"], res["distances"]), start=1
        ):
            print(f"\n[{i}] distance={dist:.3f}  id={cid}")
            print(f"    source={meta.get('source')}  title={meta.get('title')}")
            print(f"    url   : {meta.get('url')}")
            print(f"    text  : {(doc or '')[:300].replace(chr(10),' ')} ...")


if __name__ == "__main__":
    main()
