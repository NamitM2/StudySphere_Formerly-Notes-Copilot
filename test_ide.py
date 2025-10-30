#!/usr/bin/env python3
"""
Quick test script for IDE endpoints
"""
import os
import sys
from dotenv import load_dotenv
load_dotenv()

# Test imports
print("Testing imports...")
try:
    from core.ide.assignment_analyzer import AssignmentAnalyzer
    print("[OK] AssignmentAnalyzer imported")
except Exception as e:
    print(f"[FAIL] Failed to import AssignmentAnalyzer: {e}")
    sys.exit(1)

try:
    from core.ide.ai_assistant import IDEAssistant
    print("[OK] IDEAssistant imported")
except Exception as e:
    print(f"[FAIL] Failed to import IDEAssistant: {e}")
    sys.exit(1)

try:
    from api.routes_v2.ide_routes import router
    print("[OK] IDE routes imported")
except Exception as e:
    print(f"[FAIL] Failed to import IDE routes: {e}")
    sys.exit(1)

# Test analyzer
print("\nTesting AssignmentAnalyzer...")
analyzer = AssignmentAnalyzer()

test_prompt = """
Write a 5-paragraph essay analyzing the causes and effects of climate change.
Include at least 3 credible sources and cite them in MLA format.
The essay should be 1000-1500 words.
Due: Next Friday
"""

try:
    result = analyzer.analyze_assignment(test_prompt)
    print(f"[OK] Analysis successful!")
    print(f"   Type: {result['assignment_type']}")
    print(f"   Title: {result['title']}")
    print(f"   Requirements: {result['key_requirements']}")
    print(f"   Sections: {len(result['suggested_structure'].get('sections', []))}")
except Exception as e:
    print(f"[FAIL] Analysis failed: {e}")
    sys.exit(1)

print("\n[OK] All tests passed! IDE backend is working.")
print("\nNext steps:")
print("1. Make sure you've run the migration SQL in Supabase")
print("2. Go to http://localhost:5173")
print("3. Click '+ New Assignment' and paste an assignment prompt")
print("4. Try creating a project!")
