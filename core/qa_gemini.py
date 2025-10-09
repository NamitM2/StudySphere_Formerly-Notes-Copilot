# core/qa_gemini.py — Minimal RAG prompt with warm fallback + no citations
# Path: core/qa_gemini.py
from __future__ import annotations

import os
import re
from typing import Any, Dict, List, Tuple

import google.generativeai as genai

# --- Config -----------------------------------------------------------------
# Support multiple API keys with automatic fallback
API_KEYS = []
# Primary key - prefer GOOGLE_API_KEY
primary_key = os.getenv("GOOGLE_API_KEY")
if primary_key:
    API_KEYS.append(primary_key)

# Backup keys (supports up to 5 backup keys)
for i in range(1, 6):
    backup_key = os.getenv(f"GOOGLE_API_KEY_{i}")
    if backup_key and backup_key not in API_KEYS:  # Avoid duplicates
        API_KEYS.append(backup_key)

MODEL = os.getenv("GEMINI_MODEL", "gemini-2.0-flash-exp")
MAX_OUTPUT_TOKENS = int(os.getenv("GEMINI_MAX_TOKENS", "768"))
CONTEXT_CHAR_BUDGET = int(os.getenv("GEMINI_CONTEXT_CHAR_BUDGET", "24000"))  # for snippets (doubled for dynamic k)
DEFAULT_STUDENT_NAME = os.getenv("STUDENT_NAME", "Student")

# Validate configuration
if not API_KEYS:
    import sys
    print("ERROR: No API keys found in environment variables.", file=sys.stderr)
    print("Set GOOGLE_API_KEY or GOOGLE_API_KEY_1, GOOGLE_API_KEY_2, etc.", file=sys.stderr)
    sys.exit(1)

# Track which key is currently active
_current_key_index = 0


# --- Small helpers -----------------------------------------------------------
def _strip(s: str) -> str:
    return (s or "").replace("\x00", " ").strip()

def _soft_truncate(text: str, max_chars: int) -> str:
    text = _strip(text)
    if len(text) <= max_chars:
        return text
    cut = text[: max_chars - 1]
    m = re.search(r"\b[^\w]*$", cut)
    if m:
        cut = cut[: m.start()] or cut
    return cut + "…"

def _format_snippet(sn: Dict[str, Any], idx: int) -> str:
    fn = _strip(sn.get("filename") or "file")
    pg = sn.get("page")
    tx = _strip(sn.get("text") or "")
    head = f"[{idx+1}] {fn}"
    if pg is not None:
        head += f" · p.{pg}"
    return f"{head}\n{tx}"


# --- Public API --------------------------------------------------------------
def ask(
    question: str,
    snippets: List[Dict[str, Any]],
    *,
    allow_outside: bool = True,
    warm_tone: bool = True,
) -> Tuple[str, Dict[str, Any]]:
    """
    Ask Gemini a question with RAG-style snippets.

    Args
    ----
    question: str
    snippets: list of dicts with keys: filename, page, text, doc_id
    allow_outside: allow model to use stable, widely-accepted general knowledge
    warm_tone: friendlier tone (slightly higher temperature)

    Returns
    -------
    (answer_text, metadata)
      metadata is kept for future extensibility, but empty (no citations).
    """
    global _current_key_index

    question = _strip(question)
    if not question:
        return ("", {})

    if not API_KEYS:
        # No keys available → minimal local fallback
        return (_fallback_no_key(question, snippets), {})

    # Build compact context from snippets under a character budget.
    blocks: List[str] = []
    used_count = 0
    running = 0
    for i, sn in enumerate(snippets or []):
        txt = _strip((sn or {}).get("text") or "")
        if not txt:
            continue
        piece = _format_snippet(
            {
                "filename": sn.get("filename"),
                "page": sn.get("page"),
                "text": _soft_truncate(txt, 2500),
            },
            i,
        )
        delta = len(piece) + 2
        if running + delta > CONTEXT_CHAR_BUDGET and used_count > 0:
            break
        blocks.append(piece)
        running += delta
        used_count += 1

    student_name = DEFAULT_STUDENT_NAME
    context = "\n\n".join(blocks) if blocks else "No notes provided"
    num_chunks = used_count

    # Prompt: Notes-first approach with smart enrichment
    final_prompt = f"""
You are a helpful assistant for a personal Notes Q&A system.

QUESTION: {question}

RETRIEVED NOTES ({num_chunks} relevant chunks):
<<<NOTES_START>>>
{context}
<<<NOTES_END>>>

CRITICAL INSTRUCTIONS:

1. PRIMARY RULE - ALWAYS CHECK NOTES FIRST:
   - Your FIRST priority is to answer from the NOTES above.
   - If the NOTES contain ANY relevant information about the question, you MUST answer using the NOTES.
   - Even if the question seems like general knowledge, check if the NOTES have specific information about it first.
   - NOTE: You may have received more chunks than usual if the question matches many parts of the notes - synthesize ALL relevant information.

2. THREE ANSWER MODES:

   MODE A - NOTES ONLY (most common for personal/specific questions):
   - Use this when: NOTES contain relevant information
   - Answer using ONLY information from the NOTES
   - Do NOT add enrichment
   - Examples: personal info, resume details, specific course notes, project details

   MODE B - NOTES + ENRICHMENT (for general knowledge questions where notes have partial info):
   - Use this when: NOTES contain some relevant info AND the question is about well-known general knowledge
   - Start your answer with information from NOTES
   - Then add: "<<<ENRICHMENT_START>>>"
   - Then add helpful general knowledge context/enrichment
   - Examples: "What's the capital of France?" where notes mention Paris, or "Explain photosynthesis" where notes have partial info

   MODE C - GENERAL KNOWLEDGE ONLY (fallback when notes are empty/irrelevant):
   - Use this when: NOTES are empty OR completely irrelevant to the question
   - Start with: "I couldn't find an answer in your notes, but "
   - Then provide the answer from general knowledge
   - IMPORTANT: Answer common knowledge questions (science, history, geography, math) even without notes
   - Example: "How hot are volcanoes?" → "I couldn't find an answer in your notes, but volcanoes typically range from 700°C to 1,200°C (1,300°F to 2,200°F)."

3. WHEN TO USE ENRICHMENT:
   - ✅ DO enrich: General knowledge questions (capitals, math, science facts, historical events, definitions)
   - ✅ DO enrich: When notes have partial information and enrichment adds educational value
   - ❌ DON'T enrich: Personal information (projects, resume, experiences, preferences)
   - ❌ DON'T enrich: Specific course content, proprietary information, or unique details in notes
   - ❌ DON'T enrich: When you're uncertain about the enrichment content

4. ANSWER FORMAT:
   - Concise and direct (2-6 sentences for notes, 2-4 for enrichment).
   - Helpful and friendly tone.
   - No citations, source tags, or footnotes.
   - Just answer the question naturally.

5. WHEN UNCERTAIN:
   - ONLY refuse to answer if the question is about personal/specific information not in the notes
   - For general knowledge questions (science, history, geography, math, etc.), ALWAYS provide an answer using MODE C
   - If you genuinely cannot answer, say: "I couldn't find relevant information in your notes to answer this question."

NOW ANSWER THE QUESTION FOLLOWING THESE RULES STRICTLY.
""".strip()

    temperature = 0.55 if warm_tone else 0.2
    generation_config = {
        "temperature": temperature,
        "top_p": 0.9,
        "top_k": 40,
        "max_output_tokens": MAX_OUTPUT_TOKENS,
    }

    # Try each API key until one works
    last_error = None
    for attempt in range(len(API_KEYS)):
        try:
            # Configure with current key
            current_key = API_KEYS[_current_key_index]
            genai.configure(api_key=current_key)

            model = genai.GenerativeModel(MODEL)
            resp = model.generate_content(final_prompt, generation_config=generation_config)

            # Safety blocks
            if hasattr(resp, "prompt_feedback") and getattr(resp.prompt_feedback, "block_reason", None):
                reason = str(resp.prompt_feedback.block_reason)
                return (f"Sorry — I can't answer that ({reason}).", {})

            text = _strip(getattr(resp, "text", "") or "")
            if not text:
                return (_fallback_empty(), {})

            # Light cleanup: occasionally models add stray bracket refs; strip them.
            text = re.sub(r"\s*\[\d+\]\s*", " ", text)
            # Ensure we didn't slip in a "Sources" footer
            text = re.sub(r"(?i)\s*^sources:.*$", "", text, flags=re.MULTILINE).strip()

            return (text, {})

        except Exception as e:
            error_str = str(e).lower()
            # Check if it's a quota/rate limit error
            if "quota" in error_str or "429" in error_str or "resource exhausted" in error_str:
                import sys
                print(f"API key {_current_key_index + 1} quota exceeded, trying next key...", file=sys.stderr)
                last_error = e
                # Move to next key
                _current_key_index = (_current_key_index + 1) % len(API_KEYS)
                continue
            else:
                # Other errors - log and raise
                import sys
                print(f"ERROR: Gemini API call failed: {e}", file=sys.stderr)
                print(f"ERROR: Using API key index: {_current_key_index + 1}/{len(API_KEYS)}", file=sys.stderr)
                print(f"ERROR: MODEL: {MODEL}", file=sys.stderr)
                raise

    # All keys exhausted
    import sys
    print(f"ERROR: All {len(API_KEYS)} API keys exhausted", file=sys.stderr)
    if last_error:
        raise last_error
    raise RuntimeError("All API keys have exceeded their quota")


# --- Minimal fallbacks -------------------------------------------------------
def _fallback_empty() -> str:
    return "I couldn't find an answer in your notes, and I cannot answer that with my own knowledge."

def _fallback_no_key(question: str, snippets: List[Dict[str, Any]]) -> str:
    """
    Offline behavior when no API key is configured.
    Very conservative: only surfaces a couple ultra-obvious patterns from notes,
    else returns the warm not-found message.
    """
    # Try to glean a couple of trivial confirmations from snippets
    joined = " ".join(_strip((sn or {}).get('text') or "") for sn in (snippets or [])).lower()

    q = (question or "").lower()
    if any(k in joined for k in ("university of illinois", "urbana-champaign", "uiuc")):
        if any(k in q for k in ("what school", "which school", "which university", "where do i study", "university")):
            return "From your notes: you attend the University of Illinois Urbana-Champaign."
    if ("may 2029" in joined or "expected graduation" in joined) and "graduat" in q:
        return "From your notes: your expected graduation is May 2029."

    # Otherwise, warm default
    return _fallback_empty()
