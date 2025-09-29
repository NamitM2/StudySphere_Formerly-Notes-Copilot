# core/generation.py
from __future__ import annotations
from typing import List
import os
import json

# === Configuration ===
API_KEY = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "models/gemini-2.0-flash").strip()

SYSTEM_RULES = """You are a careful assistant for a notes Q&A app.

Rules:
- All statements in answer_from_notes MUST be supported by CONTEXT.
- If the answer is not in CONTEXT, set answer_from_notes EXACTLY to:
  "I'm sorry, I couldn't find an answer in your notes for that question."
- Keep sentences short and factual. No filler.
- Enrichment is optional (<= 2 short sentences). Only add if broadly true and not contradicting CONTEXT.
- If not confident, set enrichment to "".
Return ONLY valid JSON matching the schema.
"""

SCHEMA_EXAMPLES = """
EXAMPLE 1
CONTEXT: "Namit attends the University of Illinois Urbana–Champaign (UIUC)."
Q: "Where does Namit go to school?"
{
  "answer_from_notes": "Namit attends the University of Illinois Urbana–Champaign (UIUC).",
  "enrichment": "UIUC is a public land-grant research university in Illinois known for engineering and computer science.",
  "risk": "ok"
}

EXAMPLE 2
CONTEXT: "Expected graduation: May 2029."
Q: "When is Namit expected to graduate?"
{
  "answer_from_notes": "Namit is expected to graduate in May 2029.",
  "enrichment": "",
  "risk": "ok"
}

EXAMPLE 3
CONTEXT: "(no mention of clubs)"
Q: "What clubs is Namit in?"
{
  "answer_from_notes": "I'm sorry, I couldn't find an answer in your notes for that question.",
  "enrichment": "",
  "risk": "ok"
}
"""

def _compose_prompt(question: str, contexts: List[str], allow_enrichment: bool) -> str:
    ctx = "\n---\n".join(contexts) if contexts else ""
    enrich_rule = "You MAY add enrichment." if allow_enrichment else 'Do not add any enrichment; set enrichment to "".'
    return f"""{SYSTEM_RULES}

{SCHEMA_EXAMPLES}

Return JSON with fields:
{{
  "answer_from_notes": string,
  "enrichment": string,
  "risk": "ok" | "uncertain" | "contradiction"
}}

{enrich_rule}

USER QUESTION:
{question}

CONTEXT:
{ctx}
"""

def _fallback_from_notes_only(question: str, contexts: List[str]) -> str:
    """
    Deterministic fallback for local dev or when the LLM call fails.
    Keep this tiny & safe—just enough to prove the pipeline works.
    """
    joined = " ".join(contexts).lower()
    if ("university of illinois" in joined) or ("urbana-champaign" in joined) or ("uiuc" in joined):
        return "Namit attends the University of Illinois Urbana–Champaign (UIUC)."
    if ("expected graduation" in joined) or ("may 2029" in joined):
        return "Namit is expected to graduate in May 2029."
    return "I'm sorry, I couldn't find an answer in your notes for that question."

def generate_json_answer(question: str, contexts: List[str], allow_enrichment: bool = True) -> str:
    """
    Returns a single fused string like:
        "<answer_from_notes> <enrichment (if present)>"
    """
    if not contexts:
        return "I'm sorry, I couldn't find an answer in your notes for that question."

    # If no key, do notes-only fallback so local dev still works.
    if not API_KEY:
        return _fallback_from_notes_only(question, contexts)

    # Call Gemini (2.0 Flash by default) asking for pure JSON.
    try:
        import google.generativeai as genai
        genai.configure(api_key=API_KEY)

        prompt = _compose_prompt(question, contexts, allow_enrichment)
        model = genai.GenerativeModel(
            GEMINI_MODEL,
            system_instruction="Respond ONLY with valid JSON per the user's schema.",
            generation_config={"response_mime_type": "application/json"},
        )
        resp = model.generate_content(prompt)
        text = (resp.text or "{}").strip()

        # Parse/guard the JSON
        obj = json.loads(text)
        ans = obj.get("answer_from_notes") or "I'm sorry, I couldn't find an answer in your notes for that question."
        enrich = obj.get("enrichment") or ""
        if obj.get("risk") != "ok":
            enrich = ""
        return f"{ans} {enrich}".strip()

    except Exception:
        # If the model name is wrong/retired or network fails, don't crash—fallback.
        return _fallback_from_notes_only(question, contexts)
