# core/index.py
# Path: core/index.py
from __future__ import annotations
from typing import List, Sequence, Union
import numpy as np
import faiss
from sklearn.metrics.pairwise import cosine_similarity

NDArray = np.ndarray


def _l2norm(a: NDArray) -> NDArray:
    return a / (np.linalg.norm(a, axis=1, keepdims=True) + 1e-12)


class VectorIndex:
    """
    Minimal, robust FAISS wrapper with MMR reranking that uses the TRUE query
    for relevance and penalizes redundancy. If you add vectors/chunks in order,
    FAISS ids == insertion order == chunk indices.
    """

    def __init__(self, dim: int | None = None, metric: str = "ip", **kwargs):
        """
        metric: "ip" (Inner Product) or "l2"
        Accepts both dim= and dimension= for backward compatibility.
        """
        if dim is None and "dimension" in kwargs:
            dim = int(kwargs["dimension"])
        if dim is None:
            raise ValueError("VectorIndex: you must provide dim (or dimension).")

        self.dim = int(dim)
        metric = metric.lower()
        if metric not in {"ip", "l2"}:
            raise ValueError("metric must be 'ip' or 'l2'")
        self.metric = metric
        self.index = faiss.IndexFlatIP(self.dim) if metric == "ip" else faiss.IndexFlatL2(self.dim)
        self.chunks: List[str] = []

    # ---------------------------
    # Building / adding vectors
    # ---------------------------
    def add(self, vectors: NDArray, chunks: Sequence[str]) -> None:
        """
        Add a batch of vectors with matching chunk texts.
        - vectors: shape [N, dim]
        - chunks:  length N
        """
        if len(chunks) == 0:
            return
        vectors = np.asarray(vectors, dtype="float32")
        if vectors.ndim != 2 or vectors.shape[1] != self.dim:
            raise ValueError(f"vectors must be [N,{self.dim}] float32")

        if self.metric == "ip":
            vectors = _l2norm(vectors)  # IP == cosine if normalized

        self.index.add(vectors)
        self.chunks.extend(list(chunks))

    @property
    def ntotal(self) -> int:
        return int(self.index.ntotal)

    def reconstruct(self, i: int) -> NDArray:
        return self.index.reconstruct(int(i))

    # ---------------------------
    # Search + MMR rerank
    # ---------------------------
    def search(
        self,
        query_vector: Union[NDArray, Sequence[float]],
        k: int,
        diversity: float = 0.75,
    ) -> List[str]:
        """
        Return up to k context windows (prev/current/next joined with " ... ").
        Steps:
          1) Pull a candidate pool from FAISS.
          2) Compute cosine relevance to the TRUE query (not a passage).
          3) MMR to reduce redundancy.
        """
        if self.ntotal == 0:
            return []

        q = np.asarray(query_vector, dtype="float32").reshape(1, -1)
        if q.shape[1] != self.dim:
            raise ValueError(f"query_vector must have dim {self.dim}")

        # For FAISS initial search, match index preprocessing
        q_faiss = _l2norm(q) if self.metric == "ip" else q

        # 1) Candidate pool
        pool = min(max(k * 5, k), self.ntotal)
        dists, ids = self.index.search(q_faiss, pool)
        cand_ids = [int(i) for i in ids[0] if i != -1]
        if not cand_ids:
            return []

        # Reconstruct candidate vectors for consistent cosine scoring
        cand_vecs = np.array([self.reconstruct(i) for i in cand_ids], dtype="float32")

        # 2) Relevance to the TRUE query via cosine
        q_cos = _l2norm(q)  # always normalize for cosine here
        c_cos = _l2norm(cand_vecs)
        rel = cosine_similarity(q_cos, c_cos)[0]  # shape [pool]
        order = np.argsort(-rel)                  # descending relevance

        # Seed with most relevant
        selected_pos: List[int] = [int(order[0])]
        selected_ids: List[int] = [cand_ids[selected_pos[0]]]

        # 3) MMR loop
        while len(selected_ids) < min(k, len(cand_ids)):
            seln = c_cos[selected_pos]  # already-selected normalized vecs
            best_j = None
            best_score = -1e9

            for j in range(len(cand_ids)):
                if j in selected_pos:
                    continue
                r = float(rel[j])  # relevance to query
                red = float(np.max(cosine_similarity(c_cos[j:j + 1], seln)))  # redundancy
                mmr = diversity * r - (1.0 - diversity) * red
                if mmr > best_score:
                    best_score = mmr
                    best_j = j

            selected_pos.append(int(best_j))
            selected_ids.append(cand_ids[int(best_j)])

        # 4) Build small windows around each selected chunk
        results: List[str] = []
        for idx in selected_ids:
            start = max(0, idx - 1)
            end = min(len(self.chunks), idx + 2)
            results.append(" ... ".join(self.chunks[start:end]))
        return results
