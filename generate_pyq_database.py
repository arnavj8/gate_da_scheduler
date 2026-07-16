import os
import json
import requests
import sys

try:
    from pypdf import PdfReader
except ImportError:
    print("pypdf library not found. Installing it now...")
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "pypdf"])
    from pypdf import PdfReader

# Configuration
def get_openrouter_key():
    # 1. Try to load from environment variable
    key = os.environ.get("OPENROUTER_API_KEY")
    if key:
        return key
    
    # 2. Try to load from Claude Code settings file
    settings_path = os.path.expanduser("~/.claude/settings.json")
    if os.path.exists(settings_path):
        try:
            with open(settings_path, "r", encoding="utf-8") as f:
                settings = json.load(f)
                return settings.get("env", {}).get("ANTHROPIC_AUTH_TOKEN")
        except Exception:
            pass
    return None

OPENROUTER_API_KEY = get_openrouter_key()
MODEL_NAME = "google/gemini-2.5-flash"  # Fast, accurate, and cheap/free on OpenRouter
DB_FILE = "pyq_database.json"

def extract_text_from_pdf(pdf_path):
    print(f"Reading {pdf_path}...")
    reader = PdfReader(pdf_path)
    full_text = ""
    for idx, page in enumerate(reader.pages):
        text = page.extract_text()
        if text:
            full_text += f"\n--- PAGE {idx+1} ---\n{text}"
    return full_text

import re

def clean_json_string(json_str):
    """
    Cleans unescaped backslashes in LaTeX commands within a raw JSON string.
    Ensures backslashes followed by non-escape characters (e.g. \lambda, \frac)
    are properly doubled to \\lambda, \\frac.
    """
    # Known LaTeX command prefixes that start with JSON escape letters
    latex_escapes = ['neq', 'newline', 'theta', 'times', 'text', 'right', 'beta', 'frac', 'union', 'unconstrained']
    
    def repl(match):
        val = match.group(0)
        if val in [r'\\', r'\"', r'\/']:
            return val
        
        char = val[1]
        if char in 'bfnrtu':
            # Check if the matched string starts with any known LaTeX commands
            rest = val[2:]
            for prefix in latex_escapes:
                if (char + rest).startswith(prefix):
                    return '\\\\' + val[1:]
            
            # Check if it's a valid hex unicode escape (e.g. \u0020) vs a LaTeX command (e.g. \union)
            if char == 'u':
                if len(val) == 6 and all(c in '0123456789abcdefABCDEF' for c in val[2:]):
                    return val
                else:
                    return '\\\\' + val[1:]
                    
            return val
            
        return '\\\\' + val[1:]

    # Match backslash followed by a word up to 15 characters, or any single character
    pattern = r'\\[a-zA-Z]{1,15}|\\.'
    return re.sub(pattern, repl, json_str)

def call_llm_to_parse_questions(page_text, year):
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
    }
    
    prompt = f"""
You are an expert GATE Data Science & AI (DA) educator. Analyze the following text extracted from the GATE {year} DA Question Paper.
Extract all the questions found on this page. For each question, construct a JSON object matching this exact schema:

{{
  "id": <a unique integer starting from {year * 100 + 1}>,
  "year": {year},
  "subject": "<one of: Probability & Statistics, Linear Algebra, Calculus & Optimization, Programming, Data Structures & Algorithms, Database Management & Warehousing, Machine Learning, Artificial Intelligence (AI)>",
  "type": "<one of: MCQ, MSQ, NAT>",
  "question": "<The question text in LaTeX format. Use $...$ for inline math and $$...$$ for block math equations.>",
  "options": ["a) ...", "b) ...", "c) ...", "d) ..."], // empty array [] for NAT questions
  "answer": "<The correct option string (e.g. 'a) ...') or correct option key, or numerical value/range for NAT>",
  "explanation": "<A detailed step-by-step mathematical derivation and explanation in Markdown and LaTeX format.>"
}}

Guidelines:
1. Ensure all mathematical expressions are properly formatted in LaTeX using standard KaTeX notation.
2. Escape backslashes in JSON (e.g., use \\lambda instead of \lambda, \\frac instead of \frac).
3. If no question is found on the page, return an empty array [].
4. Output ONLY a valid JSON array, do not wrap in markdown blocks or include explanations outside the JSON.

Here is the extracted text:
{page_text}
"""

    payload = {
        "model": MODEL_NAME,
        "messages": [
            {"role": "user", "content": prompt}
        ],
        "max_tokens": 4096
    }
    
    try:
        response = requests.post("https://openrouter.ai/api/v1/chat/completions", headers=headers, json=payload)
        response_json = response.json()
        if "choices" not in response_json:
            print(f"OpenRouter Error: {response_json}")
            return []
        content = response_json["choices"][0]["message"]["content"].strip()
        
        # Clean up any potential markdown wraps
        if content.startswith("```json"):
            content = content[7:]
        if content.startswith("```"):
            content = content[3:]
        if content.endswith("```"):
            content = content[:-3]
        content = content.strip()
        
        # Clean up unescaped LaTeX backslashes inside JSON string
        cleaned_content = clean_json_string(content)
        return json.loads(cleaned_content)
    except Exception as e:
        print(f"Error calling LLM or parsing response: {e}")
        return []

def main():
    if not OPENROUTER_API_KEY or OPENROUTER_API_KEY.startswith("sk-or-v1-YOUR"):
        print("Please configure your OpenRouter API Key in the script.")
        return
        
    print("GATE DA PYQ Database Generator")
    print("=============================")
    
    # Check for PDF files in current directory
    pdfs = [f for f in os.listdir(".") if f.lower().endswith(".pdf")]
    if not pdfs:
        print("No PDF files found in the current directory.")
        print("Please place the official GATE DA PDF files (e.g., DA_2024.pdf, DA_2025.pdf) in this folder first.")
        return
        
    print(f"Found PDF files: {pdfs}")
    
    # Load existing database
    existing_questions = []
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, "r", encoding="utf-8") as f:
                existing_questions = json.load(f)
            print(f"Loaded {len(existing_questions)} existing questions from {DB_FILE}")
        except Exception:
            pass
            
    existing_ids = {q["id"] for q in existing_questions}
    
    for pdf in pdfs:
        # Identify year of the PDF
        pdf_lower = pdf.lower()
        if "2024" in pdf_lower:
            year = 2024
        elif "2025" in pdf_lower:
            year = 2025
        elif "2026" in pdf_lower:
            year = 2026
        else:
            try:
                year = int(input(f"Enter the year for {pdf} (e.g., 2024): "))
            except ValueError:
                print("Invalid year. Skipping this file.")
                continue
                
        text = extract_text_from_pdf(pdf)
        pages = text.split("--- PAGE ")
        
        print(f"Processing {len(pages)-1} pages of {pdf} for year {year}...")
        
        new_questions = []
        for p_idx, page in enumerate(pages):
            if not page.strip():
                continue
            print(f"Parsing Page {p_idx}...")
            questions = call_llm_to_parse_questions(page, year)
            if questions:
                for q in questions:
                    if q.get("id") not in existing_ids:
                        new_questions.append(q)
                        existing_ids.add(q["id"])
                        print(f"  Added Question: Q{q.get('id')} - {q.get('subject')}")
                        
        if new_questions:
            existing_questions.extend(new_questions)
            with open(DB_FILE, "w", encoding="utf-8") as f:
                json.dump(existing_questions, f, indent=2)
            print(f"Successfully saved {len(new_questions)} new questions to {DB_FILE}!")
        else:
            print(f"No new questions extracted from {pdf}.")
            
    print("Done!")

if __name__ == "__main__":
    main()
