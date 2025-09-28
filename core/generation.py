# core/generation.py

import os
from typing import List
import google.generativeai as genai

# The API key is now loaded by main.py
api_key = os.getenv("GOOGLE_API_KEY")
if not api_key:
    raise ValueError("GOOGLE_API_KEY not found in environment")

genai.configure(api_key=api_key)

# Using the optimal model that is confirmed to work with your key.
model = genai.GenerativeModel('gemini-2.0-flash')

def generate_answer(query: str, context: List[str]) -> str:
    context_str = "\n".join(context)
    
    # --- NEW, MORE CREATIVE PROMPT ---
    prompt = f"""
    You are a friendly and helpful study assistant called Notes Copilot. Your goal is to answer a student's question in a conversational way.

    1. First, answer the user's question directly using the provided CONTEXT from their notes. Your answer should be in a complete, natural-sounding sentence.
    2. After answering the question from the context, you MAY add a short, interesting, and relevant piece of additional information from your own general knowledge to enrich the answer. For example, if the context mentions a university, you could provide a link to its official homepage.
    3. Base your primary answer ONLY on the CONTEXT. If the answer is not in the context, say "I couldn't find the answer to that in your notes."

    CONTEXT:
    ---
    {context_str}
    ---

    QUESTION: {query}

    ANSWER:
    """
    
    try:
        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        print(f"An error occurred with the Gemini API: {e}")
        return "Sorry, I encountered an error while generating an answer."