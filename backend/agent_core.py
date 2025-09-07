# backend/agent_core.py
import requests
import json
import time
import re
import os
import sys
import threading
import uuid
import hashlib
from collections import deque
from datetime import datetime

from config import GEMINI_API_KEY
from code_executor.executor import CodeExecutor

# --- Ensure backend root is in path to find modules ---
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__))))

# --- Configuration for Gemini API ---
GEMINI_API_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash-preview-05-20:generateContent"
HEADERS = {
    "Content-Type": "application/json",
}
API_KEY = GEMINI_API_KEY
SOLVED_CHALLENGES_DIR = os.path.join(os.path.abspath(os.path.dirname(__file__)), 'solved_challenges')
os.makedirs(SOLVED_CHALLENGES_DIR, exist_ok=True)

# --- Global state for managing challenges ---
# This is a simple in-memory store. For a larger app, use a real database.
challenge_store = {}
challenge_queue = deque()

# --- Utility Functions ---
def call_gemini_api(chat_history_messages, max_retries=5, base_delay=1):
    """
    Calls the Gemini API with a given chat history for conversational context.
    Implements exponential backoff for retries.
    """
    if not isinstance(chat_history_messages, list) or \
       not all(isinstance(m, dict) and 'role' in m and 'parts' in m for m in chat_history_messages):
        raise ValueError("chat_history_messages must be a list of dictionaries with 'role' and 'parts' keys.")

    payload = {
        "contents": chat_history_messages,
        "generationConfig": {
            "temperature": 0.7,
            "maxOutputTokens": 4096,
        }
    }
    for retry_attempt in range(max_retries):
        try:
            response = requests.post(
                f"{GEMINI_API_URL}?key={API_KEY}",
                headers=HEADERS,
                data=json.dumps(payload)
            )
            response.raise_for_status()
            result = response.json()

            if result.get("candidates") and result["candidates"][0].get("content") \
               and result["candidates"][0]["content"].get("parts"):
                return result["candidates"][0]["content"]["parts"][0]["text"]
            else:
                # Log the full response to help with debugging unexpected formats
                print(f"Warning: Unexpected API response structure on attempt {retry_attempt + 1}. "
                      f"Full response: {json.dumps(result, indent=2)}")
                if retry_attempt < max_retries - 1:
                    delay = base_delay * (2 ** retry_attempt)
                    print(f"Retrying in {delay} seconds...")
                    time.sleep(delay)
                else:
                    print("Max retries reached. API call failed due to unexpected response structure.")
                    return None

        except requests.exceptions.RequestException as e:
            print(f"API request failed on attempt {retry_attempt + 1}: {e}")
            if retry_attempt < max_retries - 1:
                delay = base_delay * (2 ** retry_attempt)
                print(f"Retrying in {delay} seconds...")
                time.sleep(delay)
            else:
                print("Max retries reached. API call failed.")
                return None
        except json.JSONDecodeError:
            print(f"Failed to decode JSON response on attempt {retry_attempt + 1}.")
            if retry_attempt < max_retries - 1:
                delay = base_delay * (2 ** retry_attempt)
                print(f"Retrying in {delay} seconds...")
                time.sleep(delay)
            else:
                print("Max retries reached. API call failed.")
                return None

def extract_code(response_text):
    """
    Extracts code blocks from a Markdown formatted response, including any trailing main block.
    """
    match = re.search(r"```python\n(.*?)```", response_text, re.DOTALL)
    if match:
        return match.group(1).strip()
    return None

def get_challenge_hash(challenge_description, test_cases):
    """Generates a unique hash for a challenge based on its content."""
    content = challenge_description + json.dumps(test_cases, sort_keys=True)
    return hashlib.md5(content.encode('utf-8')).hexdigest()

def load_solved_challenge(challenge_hash):
    """Loads a previously solved challenge from the file system."""
    file_path = os.path.join(SOLVED_CHALLENGES_DIR, f"{challenge_hash}.json")
    if os.path.exists(file_path):
        with open(file_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    return None

def save_solved_challenge(challenge_hash, challenge_description, test_cases, final_code, attempts_taken):
    """Saves a successfully solved challenge to the file system."""
    file_path = os.path.join(SOLVED_CHALLENGES_DIR, f"{challenge_hash}.json")
    solution_data = {
        "challenge_description": challenge_description,
        "test_cases": test_cases,
        "final_code": final_code,
        "attempts_taken": attempts_taken,
        "solved_timestamp": datetime.utcnow().isoformat() + 'Z'
    }
    with open(file_path, 'w', encoding='utf-8') as f:
        json.dump(solution_data, f, indent=2)

def format_test_results_for_llm(test_results, max_detailed_failures=2):
    """
    Formats the test results into a readable string for the LLM,
    limiting detailed output to the first `max_detailed_failures` failing tests.
    """
    formatted_results = []
    failing_tests = [result for result in test_results if result["passed"] is False]

    if not failing_tests:
        return "All provided tests passed."

    for i, result in enumerate(failing_tests):
        if i < max_detailed_failures:
            formatted_results.append(f"Test {result['test_number']} FAILED:")
            formatted_results.append(f"  Input: {result['input']}")
            formatted_results.append(f"  Expected: {result['expected_output']}, Actual: {result['actual_output']}")
            if result["error"]:
                formatted_results.append(f"  Error: {result['error']}")
        else:
            remaining_failures = len(failing_tests) - i
            if remaining_failures > 0:
                formatted_results.append(f"... {remaining_failures} more tests failed.")
                break
    return "\n".join(formatted_results)

def solve_challenge_core(challenge_id):
    """
    Core logic for solving a challenge, running in a background thread.
    """
    challenge_data = challenge_store[challenge_id]
    challenge_description = challenge_data['description']
    test_cases = challenge_data['test_cases']
    max_attempts = challenge_data['max_attempts']
    challenge_hash = get_challenge_hash(challenge_description, test_cases)
    
    # Check if challenge is already solved
    solved_data = load_solved_challenge(challenge_hash)
    if solved_data:
        challenge_store[challenge_id]['status'] = 'solved'
        challenge_store[challenge_id]['result'] = {
            'status': 'solved',
            'final_code': solved_data['final_code'],
            'attempts_taken': solved_data['attempts_taken'],
            'message': 'Challenge solved previously, loaded from cache.'
        }
        print(f"Challenge {challenge_id} already solved. Loaded from cache.")
        return

    executor = CodeExecutor()
    chat_history = deque(maxlen=3)
    
    last_generated_code = ""

    for attempt in range(1, max_attempts + 1):
        challenge_store[challenge_id]['status'] = 'processing'
        
        current_prompt = ""
        if attempt == 1:
            current_prompt = (
                f"You are an AI programming assistant. Your task is to write a complete, runnable Python script that solves a coding problem. "
                f"The script should define a function named `solve` that takes arguments as per the problem and returns the solution. "
                f"It should also include a `if __name__ == '__main__':` block that demonstrates how to read inputs, call `solve`, and print the output. "
                f"Problem: {challenge_description}\n"
                f"Test cases with inputs and expected outputs: {json.dumps(test_cases)}\n"
                f"Provide ONLY the complete Python script within a python markdown block. Do NOT include any conversational text, explanations, or docstrings before or after the code block. Use only minimal, essential comments where logic is complex."
            )
        else:
            failing_tests_summary = format_test_results_for_llm(last_execution_report['test_results'])
            current_prompt = (
                f"The previous attempt's code failed. Here is the problem again:\n"
                f"Problem: {challenge_description}\n"
                f"And here is the code that failed:\n"
                f"```python\n{last_generated_code}\n```\n"
                f"It failed the following tests and/or encountered errors:\n"
                f"{failing_tests_summary}\n"
                f"Please debug the code and provide a corrected, complete, runnable Python script. "
                f"Provide ONLY the corrected script within a python markdown block, no explanations or docstrings. Use only minimal, essential comments."
            )

        chat_history.append({"role": "user", "parts": [{"text": current_prompt}]})
        gemini_response = call_gemini_api(list(chat_history))

        if not gemini_response:
            challenge_store[challenge_id]['status'] = 'error'
            challenge_store[challenge_id]['result'] = {
                'status': 'error',
                'message': 'Failed to get a response from Gemini API. Aborting.'
            }
            return

        chat_history.append({"role": "model", "parts": [{"text": gemini_response}]})
        last_generated_code = extract_code(gemini_response)

        if not last_generated_code:
            challenge_store[challenge_id]['status'] = 'error'
            challenge_store[challenge_id]['result'] = {
                'status': 'error',
                'message': 'No Python code block found in Gemini\'s response.'
            }
            return

        execution_report = executor.execute_code(last_generated_code, test_cases)
        last_execution_report = execution_report

        if execution_report["success"]:
            final_code = last_generated_code
            save_solved_challenge(challenge_hash, challenge_description, test_cases, final_code, attempt)
            challenge_store[challenge_id]['status'] = 'solved'
            challenge_store[challenge_id]['result'] = {
                'status': 'solved',
                'final_code': final_code,
                'attempts_taken': attempt,
                'message': 'Challenge successfully solved.'
            }
            return
        
        # Check for max attempts
        if attempt >= max_attempts:
            challenge_store[challenge_id]['status'] = 'failed'
            challenge_store[challenge_id]['result'] = {
                'status': 'failed',
                'last_code': last_generated_code,
                'attempts_taken': attempt,
                'message': f"Max attempts ({max_attempts}) reached. Could not solve the challenge.",
                'error_details': execution_report
            }
            return

def submit_challenge(payload):
    """
    Accepts a challenge from the frontend and starts a background thread to solve it.
    """
    challenge_id = f"challenge_{uuid.uuid4()}"
    challenge_store[challenge_id] = {
        'id': challenge_id,
        'status': 'submitted',
        'description': payload.get('description') or payload.get('raw_input', 'N/A'),
        'test_cases': payload.get('test_cases', []),
        'max_attempts': payload.get('max_attempts', 5),
        'result': None
    }

    # Start the solving process in a new thread
    thread = threading.Thread(target=solve_challenge_core, args=(challenge_id,))
    thread.daemon = True
    thread.start()

    return challenge_id

def parse_human_challenge_input_with_gemini(user_raw_input):
    """
    Uses Gemini to parse a human-made challenge description and test cases
    into the structured JSON format required by the agent.
    """
    parse_prompt = (
        "You are a helpful assistant designed to parse coding challenge descriptions and extract relevant information into a structured JSON format. "
        "I will provide a coding challenge in natural language, and you should output a JSON object with two top-level keys: 'description' (string) and 'test_cases' (array of objects). "
        "Each object in 'test_cases' should have an 'input' key (which should be an array even if it's a single argument, e.g., for `f(x)` the input `5` becomes `[5]`, for `f(x, y)` the inputs `1, 2` become `[1, 2]`) and an 'expected_output' key. "
        "The output should ONLY be the JSON object, without any conversational text or markdown code blocks around it.\n\n"
        "Example 1:\n"
        "User Input:\n"
        "Problem: Write a Python function `add` that takes two numbers and returns their sum.\n"
        "Test cases:\n"
        "1. Input: 1, 2. Output: 3\n"
        "2. Input: -5, 10. Output: 5\n\n"
        "Your JSON output:\n"
        "```json\n"
        "{\n"
        "  \"description\": \"Write a Python function `add` that takes two numbers and returns their sum.\",\n"
        "  \"test_cases\": [\n"
        "    {\"input\": [1, 2], \"expected_output\": 3},\n"
        "    {\"input\": [-5, 10], \"expected_output\": 5}\n"
        "  ]\n"
        "}\n"
        "```\n\n"
        "Example 2:\n"
        "User Input:\n"
        "Problem: Implement a function `is_palindrome` that checks if a string is a palindrome.\n"
        "Test cases:\n"
        "- 'madam' should return true\n"
        "- 'hello' should return false\n\n"
        "Your JSON output:\n"
        "```json\n"
        "{\n"
        "  \"description\": \"Implement a function `is_palindrome` that checks if a string is a palindrome.\",\n"
        "  \"test_cases\": [\n"
        "    {\"input\": [\"madam\"], \"expected_output\": true},\n"
        "    {\"input\": [\"hello\"], \"expected_output\": false}\n"
        "  ]\n"
        "}\n"
        "```\n\n"
        "Now, parse the following user input:\n"
        f"[USER_CHALLENGE_INPUT_START]\n{user_raw_input}\n[USER_CHALLENGE_INPUT_END]\n\n"
        "Your JSON output:"
    )

    chat_history_for_parsing = [{"role": "user", "parts": [{"text": parse_prompt}]}]
    gemini_raw_response = call_gemini_api(chat_history_for_parsing, max_retries=3)
    
    if gemini_raw_response:
        json_match = re.search(r"```json\n(.*?)```", gemini_raw_response, re.DOTALL)
        if json_match:
            json_str = json_match.group(1).strip()
        else:
            json_str = gemini_raw_response.strip()

        try:
            parsed_data = json.loads(json_str)
            if "description" in parsed_data and "test_cases" in parsed_data:
                return parsed_data
        except json.JSONDecodeError as e:
            print(f"Failed to decode JSON from Gemini's response: {e}. Raw response: {json_str}")
    
    return None
