# core/ide/assignment_analyzer.py

import re
from typing import Dict, Any, List, Optional
import google.generativeai as genai
import os

class AssignmentAnalyzer:
    """
    Analyzes assignment prompts to extract:
    - Assignment type (essay, coding, math, etc.)
    - Subject area
    - Key requirements
    - Rubric/grading criteria
    - Suggested structure
    """

    def __init__(self):
        api_key = os.getenv("GOOGLE_API_KEY")
        if not api_key:
            raise ValueError("GOOGLE_API_KEY not set")
        genai.configure(api_key=api_key)
        self.model = genai.GenerativeModel("gemini-2.0-flash-exp")

    def analyze_assignment(self, prompt_text: str) -> Dict[str, Any]:
        """
        Analyze assignment prompt and extract structured information.

        Returns:
        {
            "assignment_type": "essay",
            "subject_area": "english",
            "title": "Climate Change Analysis",
            "key_requirements": ["5-7 pages", "3+ sources", "MLA format"],
            "rubric": {...},
            "suggested_structure": {...},
            "estimated_time_minutes": 180,
            "complexity_level": "intermediate"
        }
        """

        analysis_prompt = f"""You are an expert academic advisor analyzing an assignment prompt.

ASSIGNMENT PROMPT:
{prompt_text}

Analyze this assignment and provide a structured JSON response with the following fields:

1. **assignment_type**: One of: essay, research_paper, coding, math, lab_report, worksheet, creative_writing, presentation, discussion_post
2. **subject_area**: The academic subject (english, math, science, history, computer_science, etc.)
3. **title**: A concise title for this assignment (extract or infer from prompt)
4. **key_requirements**: Array of specific requirements (page count, word count, citation style, number of sources, specific topics to cover, etc.)
5. **rubric**: If grading criteria mentioned, structure as {{"criteria_name": points, ...}}
6. **suggested_structure**: A recommended outline/structure for completing this assignment with sections
7. **estimated_time_minutes**: Estimated time to complete (in minutes)
8. **complexity_level**: One of: beginner, intermediate, advanced
9. **special_instructions**: Any unique constraints or special instructions

For suggested_structure, provide an object like:
{{
  "sections": [
    {{"name": "Introduction", "description": "Hook, background, thesis"}},
    {{"name": "Body", "description": "Main arguments"}},
    ...
  ]
}}

Return ONLY valid JSON, no markdown formatting.
"""

        try:
            response = self.model.generate_content(
                analysis_prompt,
                generation_config={
                    "temperature": 0.3,
                    "response_mime_type": "application/json"
                }
            )

            import json
            analysis = json.loads(response.text)

            # Validate required fields
            required = ["assignment_type", "subject_area", "title", "key_requirements", "suggested_structure"]
            for field in required:
                if field not in analysis:
                    analysis[field] = self._fallback_value(field, prompt_text)

            return analysis

        except Exception as e:
            print(f"[ANALYZER] Failed to analyze assignment: {e}")
            # Fallback to basic heuristics
            return self._basic_analysis(prompt_text)

    def _basic_analysis(self, prompt_text: str) -> Dict[str, Any]:
        """Fallback analysis using simple heuristics."""
        text_lower = prompt_text.lower()

        # Detect type
        if any(kw in text_lower for kw in ["essay", "write", "paper", "argument"]):
            assignment_type = "essay"
        elif any(kw in text_lower for kw in ["code", "program", "implement", "function"]):
            assignment_type = "coding"
        elif any(kw in text_lower for kw in ["solve", "equation", "proof", "calculate"]):
            assignment_type = "math"
        elif any(kw in text_lower for kw in ["lab", "experiment", "hypothesis"]):
            assignment_type = "lab_report"
        else:
            assignment_type = "essay"  # Default

        # Extract word/page count
        word_match = re.search(r'(\d+)\s*words?', text_lower)
        page_match = re.search(r'(\d+)\s*pages?', text_lower)

        requirements = []
        if word_match:
            requirements.append(f"{word_match.group(1)} words")
        if page_match:
            requirements.append(f"{page_match.group(1)} pages")

        return {
            "assignment_type": assignment_type,
            "subject_area": "general",
            "title": "Assignment",
            "key_requirements": requirements or ["Complete the assignment"],
            "suggested_structure": self._default_structure(assignment_type),
            "estimated_time_minutes": 120,
            "complexity_level": "intermediate",
            "rubric": {},
            "special_instructions": ""
        }

    def _default_structure(self, assignment_type: str) -> Dict[str, Any]:
        """Generate default structure based on assignment type."""
        structures = {
            "essay": {
                "sections": [
                    {"name": "Introduction", "description": "Hook, background, thesis statement"},
                    {"name": "Body Paragraph 1", "description": "First main point with evidence"},
                    {"name": "Body Paragraph 2", "description": "Second main point with evidence"},
                    {"name": "Body Paragraph 3", "description": "Third main point with evidence"},
                    {"name": "Conclusion", "description": "Restate thesis, summarize points, closing thoughts"}
                ]
            },
            "coding": {
                "sections": [
                    {"name": "Problem Analysis", "description": "Understand the requirements"},
                    {"name": "Algorithm Design", "description": "Plan your approach"},
                    {"name": "Implementation", "description": "Write the code"},
                    {"name": "Testing", "description": "Test with various inputs"},
                    {"name": "Documentation", "description": "Add comments and usage examples"}
                ]
            },
            "math": {
                "sections": [
                    {"name": "Given Information", "description": "List what you know"},
                    {"name": "Solution Steps", "description": "Show your work step by step"},
                    {"name": "Final Answer", "description": "State the result clearly"},
                    {"name": "Verification", "description": "Check your answer"}
                ]
            },
            "lab_report": {
                "sections": [
                    {"name": "Title", "description": "Descriptive title of experiment"},
                    {"name": "Abstract", "description": "Brief summary of experiment"},
                    {"name": "Introduction", "description": "Background and hypothesis"},
                    {"name": "Methods", "description": "Procedure and materials"},
                    {"name": "Results", "description": "Data and observations"},
                    {"name": "Discussion", "description": "Analysis and interpretation"},
                    {"name": "Conclusion", "description": "Summary of findings"},
                    {"name": "References", "description": "Cited sources"}
                ]
            }
        }

        return structures.get(assignment_type, structures["essay"])

    def _fallback_value(self, field: str, prompt_text: str) -> Any:
        """Provide fallback values for missing fields."""
        fallbacks = {
            "assignment_type": "essay",
            "subject_area": "general",
            "title": "Assignment",
            "key_requirements": ["Complete the assignment"],
            "suggested_structure": self._default_structure("essay")
        }
        return fallbacks.get(field, "")
