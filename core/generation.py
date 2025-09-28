# core/generation.py

import os
from typing import List
import google.generativeai as genai

# The API key is loaded by main.py
api_key = os.getenv("GOOGLE_API_KEY")
if not api_key:
    raise ValueError("GOOGLE_API_KEY not found in environment")

genai.configure(api_key=api_key)

# Using the exact model name you confirmed works for your key.
model = genai.GenerativeModel('gemini-2.5-pro')

def generate_answer(query: str, context: List[str]) -> str:
    context_str = "\n".join(context)
    prompt = f"""
    You are a helpful assistant for a student. Your task is to answer the student's question based ONLY on the provided context from their notes.
    Do not use any external knowledge.
    If the context does not contain the answer, say "I'm sorry, I couldn't find an answer in your notes."

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