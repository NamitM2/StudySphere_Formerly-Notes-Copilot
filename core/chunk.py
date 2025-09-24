from typing import List

def split_text(text: str, max_chars: int = 800) -> List[str]:
    chunks, buf = [], []
    for para in text.split("\n\n"):
        if sum(len(x) for x in buf) + len(para) + 2 <= max_chars:
            buf.append(para)
        else:
            if buf:
                chunks.append("\n\n".join(buf))
            buf = [para]
    if buf:
        chunks.append("\n\n".join(buf))
    return chunks
