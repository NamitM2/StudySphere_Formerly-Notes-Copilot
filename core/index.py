# core/index.py

import faiss
import numpy as np
import sqlite3
import os
from typing import List

DATA_DIR = "data"
os.makedirs(DATA_DIR, exist_ok=True)
DB_PATH = os.path.join(DATA_DIR, "chunks.db")
FAISS_INDEX_PATH = os.path.join(DATA_DIR, "faiss_index.bin")

class VectorIndex:
    def __init__(self, dimension: int):
        print(f"--- DEBUG: VectorIndex __init__ called with dimension: {dimension} ---")
        self.dimension = dimension
        self.conn = sqlite3.connect(DB_PATH)
        self.create_table()
        self.chunks: List[str] = self._load_all_chunks()
        if os.path.exists(FAISS_INDEX_PATH):
            print(f"DEBUG: Loading existing FAISS index from {FAISS_INDEX_PATH}")
            self.index = faiss.read_index(FAISS_INDEX_PATH)
            print(f"DEBUG: Loaded index has dimension: {self.index.d}")
            if self.index.d != self.dimension:
                print(f"--- DEBUG: MISMATCH FOUND! RUNNING CLEAR() ---")
                self.clear()
        else:
            print(f"--- DEBUG: CREATING NEW FAISS INDEX ---")
            self.index = faiss.IndexFlatL2(self.dimension)
            print(f"DEBUG: New index created with dimension: {self.index.d}")

    # ... (rest of the file is the same, I am just showing the top part) ...

    def _load_all_chunks(self) -> List[str]:
        cursor = self.conn.cursor()
        cursor.execute("SELECT text FROM chunks ORDER BY id ASC")
        return [row[0] for row in cursor.fetchall()]

    def create_table(self):
        cursor = self.conn.cursor()
        cursor.execute("CREATE TABLE IF NOT EXISTS chunks (id INTEGER PRIMARY KEY, text TEXT NOT NULL)")
        self.conn.commit()

    def add(self, embeddings: List[List[float]], chunks: List[str]):
        embeddings_np = np.array(embeddings).astype('float32')
        print(f"--- DEBUG: ADDING DATA ---")
        print(f"DEBUG: Dimension of index BEFORE add: {self.index.d}")
        print(f"DEBUG: Dimension of new vectors to add: {embeddings_np.shape[1]}")
        self.index.add(embeddings_np)
        cursor = self.conn.cursor()
        for chunk in chunks:
            cursor.execute("INSERT INTO chunks (text) VALUES (?)", (chunk,))
        self.conn.commit()
        self.chunks.extend(chunks)
        faiss.write_index(self.index, FAISS_INDEX_PATH)

    def search(self, query_vector: List[float], k: int) -> List[str]:
        query_np = np.array([query_vector]).astype('float32')
        distances, indices = self.index.search(query_np, k)
        results = []
        for i in indices[0]:
            if i >= 0 and i < len(self.chunks):
                start_index = max(0, i - 1)
                end_index = min(len(self.chunks), i + 2)
                context_chunk = " ... ".join(self.chunks[start_index:end_index])
                results.append(context_chunk)
        return results

    def clear(self):
        print(f"--- DEBUG: CLEARING INDEX ---")
        print(f"DEBUG: self.dimension is {self.dimension}")
        self.index = faiss.IndexFlatL2(self.dimension)
        print(f"DEBUG: Index recreated. New dimension is: {self.index.d}")
        cursor = self.conn.cursor()
        cursor.execute("DELETE FROM chunks")
        self.conn.commit()
        self.chunks = []
        if os.path.exists(FAISS_INDEX_PATH):
            os.remove(FAISS_INDEX_PATH)
        print("--- DEBUG: CLEAR COMPLETE ---")