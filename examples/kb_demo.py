"""V1 demo: ingest a paper and run a semantic search against it."""

import asyncio
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

from src.core.kb_store.database import init_db
from src.core.kb_store.paper_store import PaperStore
from src.core.kb_store.chunk_store import ChunkStore
from src.core.kb_query.retriever import KBRetriever
from src.core.embedding.openai_embedder import OpenAIEmbedder
from src.core.models import Paper, PaperChunk
from src.core.pdf_ingest import download_pdf, parse_pdf, chunk_text


async def main():
    db_path = Path("./data/demo_kb.sqlite")
    conn = init_db(db_path)
    paper_store = PaperStore(conn)
    chunk_store = ChunkStore(conn)
    embedder = OpenAIEmbedder()
    retriever = KBRetriever(chunk_store, embedder)

    # Ingest one arXiv paper
    pdf_url = "https://arxiv.org/pdf/1706.03762.pdf"  # Attention Is All You Need
    paper = Paper(source="arxiv", external_id="1706.03762", title="Attention Is All You Need", url_pdf=pdf_url)
    paper_id = paper_store.upsert(paper)
    print(f"Upserted paper: {paper_id}")

    if chunk_store.count_by_paper(paper_id) == 0:
        print("Downloading and parsing PDF…")
        pdf_path = await download_pdf(pdf_url)
        text = parse_pdf(pdf_path)
        raw_chunks = chunk_text(text)
        chunks = [PaperChunk(paper_id=paper_id, chunk_index=i, text=c) for i, c in enumerate(raw_chunks)]
        print(f"Embedding {len(chunks)} chunks…")
        embeddings = await embedder.embed([c.text for c in chunks])
        for chunk, emb in zip(chunks, embeddings):
            chunk.embedding = emb
        chunk_store.insert_chunks(chunks)
        print("Ingestion complete.")
    else:
        print("Paper already ingested, skipping download.")

    print("\nSearching: 'multi-head self-attention'")
    results = await retriever.search("multi-head self-attention", top_k=3)
    for r in results:
        print(f"  score={r.score:.4f}  chunk={r.chunk_index}  preview={r.text[:120]!r}")


if __name__ == "__main__":
    asyncio.run(main())
