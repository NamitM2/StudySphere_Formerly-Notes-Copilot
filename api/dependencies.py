# api/dependencies.py - DEPRECATED
# This file is no longer used. The main embedding system is in core/embeddings.py
# and search functionality uses PostgreSQL vector search in core/search_pg.py
#
# This file was creating import conflicts and is being phased out.
# If you need embedding functionality, use core/embeddings.py instead.
#
# TODO: Remove this file once confirmed no longer needed.

# from __future__ import annotations
# from sentence_transformers import SentenceTransformer
# from core.index import VectorIndex

# Use the same model for both passages and queries
# MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"
# _embed_model = SentenceTransformer(MODEL_NAME)
# EMBED_DIM = _embed_model.get_sentence_embedding_dimension()  # MiniLM-L6-v2 => 384

# Export: embedding helper + global index
# def embed_chunks(texts: list[str]):
#     # normalize to float32 and (for IP) we'll normalize inside VectorIndex.add()
#     return _embed_model.encode(texts, normalize_embeddings=False).astype("float32")

# Global in-memory index; use metric="ip" (cosine with normalization in index.add)
# vector_index = VectorIndex(dim=EMBED_DIM, metric="ip")
