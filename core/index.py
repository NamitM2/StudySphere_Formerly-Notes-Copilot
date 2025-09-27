# core/index.py

# == IMPORTS =================================================================
# These are the tools we need for this file.

# FAISS is the library from Facebook for fast vector searching.
import faiss

# NumPy is a library for high-performance numerical operations. FAISS is
# built on top of NumPy, so they work together. We use the standard
# alias 'np' for numpy.
import numpy as np
from typing import List


# == THE VECTOR INDEX CLASS ==================================================
# A blueprint for our searchable "vector library".

class VectorIndex:
    def __init__(self, dimension: int):
        """
        The constructor for our class. This runs when we create a new VectorIndex.
        - dimension: The size of our vectors (e.g., 384 for the model we're using).
        """
        # The dimension of the vectors we'll be storing. For the
        # 'all-MiniLM-L6-v2' model, this is 384.
        self.dimension = dimension
        
        # We create a FAISS index. 'IndexFlatL2' is a basic but effective
        # type of index. It performs an exhaustive search, which is fine
        # for our needs. 'L2' refers to the distance metric (Euclidean distance).
        self.index = faiss.IndexFlatL2(self.dimension)
        
        # We also need a simple way to store the original text chunks.
        # This list will map the index ID from FAISS back to the actual text.
        self.chunks: List[str] = []

    def add(self, embeddings: List[List[float]], chunks: List[str]):
        """
        Adds new vectors and their corresponding text chunks to the index.
        """
        # FAISS requires the embeddings to be in a specific format: a NumPy
        # array of type float32. This line handles the conversion.
        embeddings_np = np.array(embeddings).astype('float32')
        
        # This is the command to add the new vectors to the FAISS index.
        self.index.add(embeddings_np)
        
        # We store the original text chunks in our mapping list.
        self.chunks.extend(chunks)
        
        print(f"Added {len(chunks)} chunks to the index.")
        print(f"Index now contains {self.index.ntotal} total vectors.")

    def search(self, query_vector: List[float], k: int) -> List[str]:
        """
        Searches the index for the top 'k' most similar vectors.
        - query_vector: The vector representation of the user's question.
        - k: The number of results to return.
        """
        # First, we convert the user's query vector into the NumPy format.
        query_np = np.array([query_vector]).astype('float32')
        
        # This is the core search operation. It returns two things:
        # D: A list of distances (how far away each result is).
        # I: A list of indices (the IDs of the top 'k' most similar vectors).
        distances, indices = self.index.search(query_np, k)
        
        # We use the indices returned by FAISS to look up the original
        # text chunks from our simple list. This is a list comprehension,
        # a concise way to create a list in Python.
        results = [self.chunks[i] for i in indices[0]]
        
        return results