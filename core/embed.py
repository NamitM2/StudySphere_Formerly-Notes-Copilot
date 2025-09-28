# core/embed.py

# == IMPORTS =================================================================
# These are the tools we need for this file.

# 'List' is a "type hint." It helps us write cleaner code by specifying
# that we expect a list of items, making the code easier for humans to read.
from typing import List

# This is the most important tool. We're importing the main class,
# 'SentenceTransformer', from the library we installed earlier.
from sentence_transformers import SentenceTransformer


# == MODEL LOADING ===========================================================
# We load the AI model into memory. We do this here, outside of any function,
# so it only happens ONCE when the application starts up. This is much more
# efficient than reloading the model every time a file is uploaded.

print("Loading embedding model (this may take a moment)...")

# We create an instance of the model. 'all-MiniLM-L6-v2' is a specific, popular,
# and efficient pre-trained model. The first time this line runs, the library
# will automatically download the model files (about 227MB) from the internet
# and store them on your computer for future use.

# OLD: model = SentenceTransformer('multi-qa-MiniLM-L6-cos-v1')
model = SentenceTransformer('all-mpnet-base-v2') # NEW & MORE POWERFUL

print("Embedding model loaded successfully.")


# == THE EMBEDDING FUNCTION =================================================
# This is our reusable tool for turning text into vectors.

def embed_chunks(chunks: List[str]) -> List[List[float]]:
    """
    This function takes a list of text chunks and returns a list of embeddings.

    - chunks: A list of strings (e.g., ["This is chunk one.", "This is chunk two."])
    - returns: A list of lists of floats (e.g., [[0.1, -0.5, ...], [0.3, 0.8, ...]])
    """
    
    # This is the core of the process. The .encode() method is part of the
    # SentenceTransformer model. It takes our list of text chunks as input.
    # The AI model then processes each chunk and outputs a numerical vector for it.
    # The output is a special kind of array from a library called NumPy.
    # The .tolist() method is a convenient way to convert that special array
    # into a standard Python list, which is easier to work with.
    embeddings = model.encode(chunks).tolist()
    
    # A helpful print statement to see how many embeddings were created.
    print(f"Generated {len(embeddings)} embeddings for {len(chunks)} chunks.")
    
    # The function returns the final list of vectors.
    return embeddings