# core/ide/ai_assistant.py

import google.generativeai as genai
import os
from typing import Dict, Any, Optional, List

class IDEAssistant:
    """
    AI assistant for the Assignment IDE.

    Provides:
    - Autocomplete suggestions
    - Smart suggestions for next steps
    - Content generation with guardrails
    - Review and feedback
    """

    def __init__(self):
        api_key = os.getenv("GOOGLE_API_KEY")
        if not api_key:
            raise ValueError("GOOGLE_API_KEY not set")
        genai.configure(api_key=api_key)
        self.model = genai.GenerativeModel("gemini-2.0-flash-exp")

    def autocomplete(
        self,
        current_text: str,
        cursor_position: int,
        assignment_context: Dict[str, Any],
        max_tokens: int = 50
    ) -> str:
        """
        Provide autocomplete suggestion at cursor position.

        Returns: Suggested completion text (not full text, just the completion)
        """

        # Get text before and after cursor
        before_cursor = current_text[:cursor_position]
        after_cursor = current_text[cursor_position:]

        # Get last sentence/paragraph for context
        context_start = max(0, cursor_position - 500)
        local_context = current_text[context_start:cursor_position]

        prompt = f"""You are an intelligent writing assistant helping a student complete their assignment.

ASSIGNMENT TYPE: {assignment_context.get('assignment_type', 'essay')}
ASSIGNMENT TOPIC: {assignment_context.get('title', 'Assignment')}
REQUIREMENTS: {', '.join(assignment_context.get('key_requirements', []))}

CURRENT CONTEXT (last 500 characters):
{local_context}

INSTRUCTION: Provide a natural, helpful completion (1-2 sentences max) that:
1. Continues the thought naturally
2. Is relevant to the assignment topic
3. Helps the student express their OWN ideas (don't write their full answer)
4. Uses appropriate academic language

Provide ONLY the completion text, no explanations or markdown.
"""

        try:
            response = self.model.generate_content(
                prompt,
                generation_config={
                    "temperature": 0.7,
                    "max_output_tokens": max_tokens
                }
            )

            completion = response.text.strip()

            # Remove any quotes or markdown
            completion = completion.strip('"\'`')

            return completion

        except Exception as e:
            print(f"[AUTOCOMPLETE] Error: {e}")
            return ""

    def suggest_next_steps(
        self,
        current_text: str,
        assignment_context: Dict[str, Any],
        current_section: Optional[str] = None
    ) -> List[Dict[str, str]]:
        """
        Suggest next steps/actions for the student.

        Returns: List of suggestions
        """

        word_count = len(current_text.split())
        structure = assignment_context.get('suggested_structure', {})
        sections = structure.get('sections', [])

        assignment_prompt = assignment_context.get('assignment_prompt', '')
        subject_area = assignment_context.get('subject_area', '')

        prompt = f"""You are a helpful tutor guiding a student through their assignment.

ORIGINAL ASSIGNMENT PROMPT: {assignment_prompt}

ASSIGNMENT DETAILS:
- Title: {assignment_context.get('title')}
- Type: {assignment_context.get('assignment_type')}
- Subject: {subject_area}
- Current Section: {current_section or 'Working on content'}
- Current Word Count: {word_count}
- Target Requirements: {', '.join(assignment_context.get('key_requirements', []))}

SUGGESTED STRUCTURE:
{self._format_structure(sections)}

CURRENT CONTENT (last 1000 characters):
{current_text[-1000:] if current_text else '[No content yet]'}

Based on the SPECIFIC ASSIGNMENT TOPIC and where the student is in their work, suggest 3-5 concrete, actionable next steps. For each suggestion:
1. What action should they take? (Be SPECIFIC to the assignment topic - e.g., for climate change essay, mention actual climate change concepts)
2. Why is it important?
3. Brief tip on how to do it

Format as JSON array:
[
  {{"action": "Action title", "explanation": "Why and how", "priority": "high"}},
  ...
]

Return ONLY valid JSON. Make suggestions SPECIFIC to the assignment topic, not generic writing advice.
"""

        try:
            response = self.model.generate_content(
                prompt,
                generation_config={
                    "temperature": 0.5,
                    "response_mime_type": "application/json"
                }
            )

            import json
            suggestions = json.loads(response.text)
            return suggestions

        except Exception as e:
            print(f"[SUGGESTIONS] Error: {e}")
            return self._default_suggestions(assignment_context)

    def improve_content(
        self,
        current_text: str,
        assignment_context: Dict[str, Any]
    ) -> List[Dict[str, str]]:
        """
        Analyze content and provide specific improvement suggestions.
        Returns list of {original, improved, reason} suggestions.
        """
        if not current_text or len(current_text) < 50:
            return []

        # Split into sentences for analysis
        sentences = [s.strip() + '.' for s in current_text.split('.') if s.strip()]

        # Analyze last few sentences for improvements
        recent_text = '. '.join(sentences[-5:]) if len(sentences) > 5 else current_text

        prompt = f"""You are a writing improvement assistant. Analyze this text and suggest specific improvements.

ASSIGNMENT CONTEXT:
- Topic: {assignment_context.get('assignment_prompt', '')}
- Type: {assignment_context.get('assignment_type', '')}
- Subject: {assignment_context.get('subject_area', '')}

TEXT TO IMPROVE:
{recent_text}

Find 1-3 specific sentences or phrases that could be improved. For each:
1. Identify the exact text that needs improvement
2. Provide a better version
3. Explain why it's better

Return as JSON array:
[
  {{
    "original": "exact text from document",
    "improved": "improved version",
    "reason": "why this is better"
  }}
]

Focus on:
- Clarity and conciseness
- Grammar and style
- Academic tone appropriate for the subject
- Stronger word choices
- Better sentence structure

Return ONLY valid JSON. If no improvements needed, return empty array [].
"""

        try:
            response = self.model.generate_content(
                prompt,
                generation_config={
                    "temperature": 0.3,
                    "response_mime_type": "application/json"
                }
            )

            import json
            suggestions = json.loads(response.text)

            # Filter to only include suggestions where original text actually exists in content
            valid_suggestions = [
                s for s in suggestions
                if s.get('original') and s['original'].lower() in current_text.lower()
            ]

            return valid_suggestions[:3]  # Max 3 suggestions at a time

        except Exception as e:
            print(f"[IMPROVE_CONTENT] Error: {e}")
            return []

    def chat(
        self,
        user_message: str,
        current_text: str,
        assignment_context: Dict[str, Any],
        chat_history: List[Dict[str, str]] = []
    ) -> Dict[str, Any]:
        """
        General chat interface - no restrictions, can complete work.
        """
        assignment_prompt = assignment_context.get('assignment_prompt', '')
        subject_area = assignment_context.get('subject_area', '')

        # Build conversation history
        history_text = "\n".join([
            f"{'Student' if msg['role'] == 'user' else 'Assistant'}: {msg['content']}"
            for msg in chat_history[-5:]  # Last 5 messages for context
        ])

        prompt = f"""You are an AI writing assistant helping a student with their assignment. You can provide complete help, write content, finish essays, make revisions - whatever they need.

ASSIGNMENT: {assignment_prompt}
TYPE: {assignment_context.get('assignment_type')}
SUBJECT: {subject_area}
REQUIREMENTS: {', '.join(assignment_context.get('key_requirements', []))}

CURRENT CONTENT:
{current_text if current_text else '[Empty document]'}

CONVERSATION HISTORY:
{history_text if history_text else '[New conversation]'}

STUDENT REQUEST: {user_message}

Based on what the student is asking for:
1. If they want you to write something, write it completely and well
2. If they want revisions, provide the revised version
3. If they want to finish the essay, complete it for them
4. If they ask a question, answer it clearly

Provide a natural, helpful response. If you generate content they can insert into their document, make it clear that's what you're doing.
"""

        try:
            response = self.model.generate_content(
                prompt,
                generation_config={
                    "temperature": 0.7,
                    "max_output_tokens": 2048
                }
            )

            response_text = response.text.strip()

            # Determine if this is insertable content
            action = "insert" if any(word in user_message.lower() for word in ['write', 'finish', 'complete', 'add', 'create', 'generate']) else "inform"

            return {
                "response": response_text,
                "action": action,
                "generated_text": response_text if action == "insert" else None
            }

        except Exception as e:
            print(f"[CHAT] Error: {e}")
            return {
                "response": "I encountered an error. Could you rephrase your request?",
                "action": "inform",
                "generated_text": None
            }

    def generate_content(
        self,
        user_request: str,
        current_text: str,
        assignment_context: Dict[str, Any],
        generation_mode: str = "scaffold"
    ) -> Dict[str, Any]:
        """
        Generate content based on user request.

        Modes:
        - scaffold: Provide outline/structure (no full text)
        - draft: Generate a rough draft with placeholders
        - expand: Elaborate on existing text
        """

        system_instructions = {
            "scaffold": "Provide a complete, detailed outline or structure with specific suggestions.",
            "draft": "Generate a complete rough draft with full paragraphs and content.",
            "expand": "Elaborate on the existing text with complete, well-written additions."
        }

        prompt = f"""You are a writing assistant helping with an assignment. Write complete, high-quality content.

ASSIGNMENT: {assignment_context.get('title')}
TYPE: {assignment_context.get('assignment_type')}

STUDENT'S REQUEST: {user_request}

CURRENT TEXT:
{current_text[-2000:] if current_text else "[No content yet]"}

MODE: {generation_mode}
INSTRUCTION: {system_instructions.get(generation_mode, system_instructions['scaffold'])}

Write complete, polished content that can be used directly in the document.
"""

        try:
            response = self.model.generate_content(
                prompt,
                generation_config={
                    "temperature": 0.6,
                    "max_output_tokens": 1000
                }
            )

            generated = response.text.strip()

            return {
                "generated_text": generated,
                "is_scaffold": generation_mode == "scaffold",
                "suggestions": None,
                "warning": None
            }

        except Exception as e:
            print(f"[GENERATION] Error: {e}")
            return {
                "generated_text": "",
                "error": str(e)
            }

    def review_work(
        self,
        content: str,
        assignment_context: Dict[str, Any],
        focus_areas: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Review student's work and provide feedback.
        """

        focus = focus_areas or ["structure", "clarity", "completeness"]

        prompt = f"""You are a helpful teacher reviewing a student's assignment draft.

ASSIGNMENT: {assignment_context.get('title')}
TYPE: {assignment_context.get('assignment_type')}
REQUIREMENTS: {', '.join(assignment_context.get('key_requirements', []))}

FOCUS AREAS FOR REVIEW: {', '.join(focus)}

STUDENT'S WORK:
{content}

Provide constructive feedback focusing on:
1. What the student is doing well (be specific!)
2. Areas that need improvement (with actionable suggestions)
3. Specific suggestions for next steps

Format as JSON:
{{
  "overall_feedback": "Brief summary of current quality",
  "strengths": ["Strength 1", "Strength 2", ...],
  "areas_for_improvement": [
    {{"issue": "Description", "suggestion": "How to fix it"}},
    ...
  ],
  "completion_percentage": 75,
  "meets_requirements": true
}}

Be encouraging but honest. Help the student improve their own work.
"""

        try:
            response = self.model.generate_content(
                prompt,
                generation_config={
                    "temperature": 0.4,
                    "response_mime_type": "application/json"
                }
            )

            import json
            feedback = json.loads(response.text)
            return feedback

        except Exception as e:
            print(f"[REVIEW] Error: {e}")
            return {
                "overall_feedback": "Unable to generate feedback at this time.",
                "error": str(e)
            }

    def _format_structure(self, sections: List[Dict]) -> str:
        """Format structure sections for prompt."""
        return "\n".join([
            f"- {s['name']}: {s.get('description', '')}"
            for s in sections
        ])

    def _default_suggestions(self, assignment_context: Dict) -> List[Dict]:
        """Fallback suggestions if AI fails."""
        return [
            {
                "action": "Review the assignment requirements",
                "explanation": "Make sure you understand what's being asked",
                "priority": "high"
            },
            {
                "action": "Create an outline",
                "explanation": "Plan your structure before writing",
                "priority": "high"
            },
            {
                "action": "Start with a strong thesis",
                "explanation": "Clearly state your main argument or goal",
                "priority": "medium"
            }
        ]

    def _get_ethical_reminder(self, mode: str) -> str:
        """Get appropriate ethical reminder based on generation mode."""
        reminders = {
            "scaffold": "This is a framework - fill it in with YOUR own ideas and analysis.",
            "draft": "This is a starting point - revise thoroughly and add your personal insights.",
            "expand": "Review this expansion and adjust to match your voice and perspective."
        }
        return reminders.get(mode, "Remember to make this work your own.")
