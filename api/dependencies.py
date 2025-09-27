# api/dependencies.py

from core.index import VectorIndex

# This is the single, shared instance of our VectorIndex.
# By creating it here, other files can import it without circular dependencies.
vector_index = VectorIndex(dimension=384)