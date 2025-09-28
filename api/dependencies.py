# api/dependencies.py

from core.index import VectorIndex

# We no longer need to load dotenv here.
# The VectorIndex is created, and the rest of the app assumes the
# environment variables have been set in the terminal.

vector_index = VectorIndex(dimension=768)