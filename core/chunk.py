# core/chunk.py

def split_text(text: str) -> list[str]:
    """
    Splits the text by lines and filters out empty or very short lines.
    """
    # Split the text by single newlines.
    lines = text.split('\n')
    
    # Use a list comprehension to create a list of non-empty, stripped lines.
    # We'll filter out any lines that are shorter than, say, 5 characters.
    chunks = [line.strip() for line in lines if len(line.strip()) > 5]
    
    return chunks