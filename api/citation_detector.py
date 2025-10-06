"""
Citation detection logic - determines if answer is from notes or model knowledge.
"""

# Debug logging
import sys
import datetime

def should_show_citations(answer: str, min_distance: float) -> bool:
    """
    Determine if citations should be shown based on answer content and document relevance.

    Args:
        answer: The generated answer text
        min_distance: Minimum cosine distance to retrieved documents (lower = more similar)

    Returns:
        True if citations should be shown (answer is from notes)
        False if answer is from model knowledge
    """
    answer_lower = answer.lower() if isinstance(answer, str) else ""

    # Check if answer explicitly says it's not in notes
    # Handle both straight (') and curly (') apostrophes
    has_not_found_phrase = (
        ("couldn't find" in answer_lower or "couldn't find" in answer_lower or
         "could not find" in answer_lower or
         "can't find" in answer_lower or "can't find" in answer_lower or
         "cannot find" in answer_lower)
        and "notes" in answer_lower
    )

    # Check if retrieved documents are actually relevant
    # Distance < 0.3 means high similarity (cosine distance, lower is better)
    has_relevant_docs = min_distance < 0.3

    # Show citations only if answer is from notes
    is_from_notes = (not has_not_found_phrase) and has_relevant_docs

    # Debug log to both file and stderr
    log_msg = f"{datetime.datetime.now()}: answer={answer[:50]}, min_dist={min_distance:.3f}, has_not_found={has_not_found_phrase}, has_relevant={has_relevant_docs}, show_cites={is_from_notes}"
    try:
        with open("citation_check.log", "a", encoding="utf-8") as f:
            f.write(log_msg + "\n")
    except:
        pass

    # Also print to stderr so we can see it in the console
    print(f"[CITATION_DETECTOR] {log_msg}", file=sys.stderr)

    return is_from_notes
