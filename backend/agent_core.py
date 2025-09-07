# backend/agent_core.py
import requests
import json
import time
import re
from collections import deque
import os
import hashlib
from datetime import datetime

# Adjust imports to be relative to the 'backend' directory
from config import GEMINI_API_KEY
from code_executor.executor import CodeExecutor

# --- Configuration for Gemini API ---
GEMINI_API_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash-preview-05-20:generateContent"
HEADERS = {
    "Content-Type": "application/json",
}
API_KEY = GEMINI_API_KEY

# --- Solved Challenges Directory ---
# Path needs to be relative to the backend directory where agent_core.py is
SOLVED_CHALLENGES_DIR = os.path.join(os.path.dirname(__file__), "solved_challenges")
os.makedirs(SOLVED_CHALLENGES_DIR, exist_ok=True)

# --- Function to make API call with exponential backoff ---
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
            "maxOutputTokens": 409600,
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
                # Log full response for debugging when content is missing
                print(f"Warning: Unexpected API response structure on attempt {retry_attempt + 1}. "
                      f"Full response: {json.dumps(result, indent=2)}")
                if retry_attempt < max_retries - 1:
                    delay = base_delay * (2 ** retry_attempt)
                    time.sleep(delay)
                else:
                    print("Max retries reached. API call failed due to unexpected response structure.")
                    return None

        except requests.exceptions.RequestException as e:
            print(f"API request failed on attempt {retry_attempt + 1}: {e}")
            if retry_attempt < max_retries - 1:
                delay = base_delay * (2 ** retry_attempt)
                time.sleep(delay)
            else:
                print("Max retries reached. API call failed.")
                return None
        except json.JSONDecodeError:
            print(f"Failed to decode JSON response on attempt {retry_attempt + 1}.")
            if retry_attempt < max_retries - 1:
                delay = base_delay * (2 ** retry_attempt)
                time.sleep(delay)
            else:
                print("Max retries reached. API call failed.")
                return None

def extract_python_code(response_text):
    """
    Extracts Python code blocks from a Markdown formatted response.
    Assumes the code is within triple backticks with 'python' specified.
    """
    match = re.search(r"```python\n(.*?)```", response_text, re.DOTALL)
    if match:
        return match.group(1).strip()
    return None

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

def get_challenge_hash(challenge_description, test_cases):
    """Generates a unique hash for a challenge based on its description and test cases."""
    challenge_str = challenge_description + json.dumps(test_cases, sort_keys=True) + "python"
    return hashlib.md5(challenge_str.encode('utf-8')).hexdigest()

def load_solved_challenge(challenge_hash):
    """
    Loads a previously solved challenge from the solved_challenges directory.
    Returns the solved data if found, otherwise None.
    """
    file_path = os.path.join(SOLVED_CHALLENGES_DIR, f"{challenge_hash}.json")
    if os.path.exists(file_path):
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except json.JSONDecodeError as e:
            print(f"Warning: Corrupted solved challenge file {file_path}: {e}")
            return None
    return None

def save_solved_challenge(challenge_hash, challenge_description, test_cases, final_code, attempts_taken):
    """
    Saves a successfully solved challenge to the solved_challenges directory.
    """
    solved_data = {
        "challenge_description": challenge_description,
        "test_cases": test_cases,
        "final_code": final_code,
        "attempts_taken": attempts_taken,
        "solved_timestamp": datetime.now().isoformat(),
        "language": "python"
    }
    file_path = os.path.join(SOLVED_CHALLENGES_DIR, f"{challenge_hash}.json")
    try:
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(solved_data, f, indent=2)
        print(f"Solution saved to {file_path}")
    except Exception as e:
        print(f"Error saving solution to file {file_path}: {e}")

def solve_challenge_core(challenge_description, test_cases, max_attempts=5):
    """
    Attempts to solve a coding challenge using Gemini, running tests via Docker,
    and iteratively debugging until successful or max attempts reached.
    (Assumes Python for code generation and execution).
    Returns a dictionary with result and final code/error.
    """
    executor = CodeExecutor()
    chat_history = deque(maxlen=3)

    print(f"\n--- Attempting to solve challenge in Python: {challenge_description[:80]}... ---")

    challenge_hash = get_challenge_hash(challenge_description, test_cases)
    existing_solution = load_solved_challenge(challenge_hash)
    if existing_solution:
        print(f"Challenge already solved! Loading solution from {os.path.join(SOLVED_CHALLENGES_DIR, f'{challenge_hash}.json')}")
        return {
            "status": "solved",
            "final_code": existing_solution['final_code'],
            "attempts_taken": existing_solution['attempts_taken'],
            "message": "Challenge already solved, loaded from disk."
        }


    for attempt in range(1, max_attempts + 1):
        print(f"\nAttempt {attempt}/{max_attempts}...")

        current_prompt = ""
        if attempt == 1:
            current_prompt = (
                f"You are an AI programming assistant. Your task is to write a Python function.\n"
                f"Problem: {challenge_description}\n"
                f"Write a Python function named `solve` that correctly implements the solution. "
                f"Ensure the function signature (including parameter types and return type) matches the problem's requirements. "
                f"Provide minimal and only necessary comments. Do NOT include extensive docstrings or block comments.\n" # Modified prompt
                f"Here are example test cases with their inputs and expected outputs to guide you:\n"
                f"{json.dumps(test_cases, indent=2)}\n"
                f"Provide ONLY the Python code block (including imports if any) within a python markdown block. Do NOT include any conversational text before or after the code block."
            )
        else:
            failing_tests_summary = format_test_results_for_llm(last_execution_report['test_results'])
            current_prompt = (
                f"Your previous Python code for the problem: '{challenge_description[:100]}...' failed some tests.\n"
                f"Here is the failed code:\n"
                f"```python\n{last_generated_code}\n```\n"
                f"The following tests failed (or errors occurred):\n"
                f"{failing_tests_summary}\n"
                f"Carefully review the problem, the failed code, and the test results. Identify the bugs and provide the corrected Python function `solve`. "
                f"Provide minimal and only necessary comments. Do NOT include extensive docstrings or block comments.\n" # Modified prompt
                f"Provide ONLY the corrected Python code block (including imports if any) within a python markdown block. Do NOT include any conversational text before or after the code block."
            )

        chat_history.append({"role": "user", "parts": [{"text": current_prompt}]})
        gemini_response = call_gemini_api(list(chat_history))

        if not gemini_response:
            print("Failed to get a response from Gemini API. Aborting.")
            return {
                "status": "error",
                "message": "Failed to get response from Gemini API."
            }

        chat_history.append({"role": "model", "parts": [{"text": gemini_response}]})

        last_generated_code = extract_python_code(gemini_response)

        if not last_generated_code:
            print("No Python code block found in Gemini's response. Aborting.")
            return {
                "status": "error",
                "message": "No valid Python code block found in Gemini's response."
            }

        print("\nExtracted Python Code:")
        print(last_generated_code)

        execution_report = executor.execute_code(last_generated_code, test_cases, language="python")
        last_execution_report = execution_report

        print("\n--- Docker Execution Report ---")
        if execution_report["success"]:
            print("Overall Status: SUCCESS 🎉")
            print(f"Challenge solved in {attempt} attempts!")
            save_solved_challenge(challenge_hash, challenge_description, test_cases, last_generated_code, attempt)
            return {
                "status": "solved",
                "final_code": last_generated_code,
                "attempts_taken": attempt,
                "message": "Challenge successfully solved."
            }
        else:
            print("Overall Status: FAILED ❌")
            # For API, we return detailed error info
            error_details = {
                "message": "Code failed tests.",
                "error_message": execution_report.get("error_message"),
                "exception_type": execution_report.get("exception_type"),
                "test_results": execution_report.get("test_results")
            }
            if attempt < max_attempts:
                print(f"Code failed. Retrying with debugging prompt in a moment...")
                time.sleep(2)
            else:
                print(f"Max attempts ({max_attempts}) reached. Could not solve the challenge.")
                return {
                    "status": "failed",
                    "final_code": last_generated_code,
                    "attempts_taken": attempt,
                    "error_details": error_details,
                    "message": "Challenge could not be solved within max attempts."
                }
    return {
        "status": "error",
        "message": "An unexpected state occurred in solve_challenge_core."
    }


def parse_human_challenge_input_with_gemini(user_raw_input, max_retries=3, base_delay=1):
    """
    Uses Gemini to parse a human-made challenge description and test cases
    into the structured JSON format required by the agent.
    (Assumes Python for the challenge).
    """
    parse_prompt = (
        "You are a helpful assistant designed to parse coding challenge descriptions and extract relevant information into a structured JSON format. "
        "I will provide a coding challenge in natural language, and you should output a JSON object with two top-level keys: 'description' (string) and 'test_cases' (array of objects). "
        "Each object in 'test_cases' should have an 'input' key (which should be an array even if it's a single argument, e.g., for `f(x)` the input `5` becomes `[5]`, for `f(x, y)` the inputs `1, 2` become `[1, 2]`) and an 'expected_output' key. "
        "Please make sure the 'input' values are correctly structured as an array for the `solve` function call. "
        "Assume the programming language for the solution is Python.\n"
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

    for attempt in range(max_retries):
        print(f"Parsing natural language input (Attempt {attempt + 1}/{max_retries})...")
        gemini_raw_response = call_gemini_api(chat_history_for_parsing, max_retries=1)
        
        if gemini_raw_response:
            json_match = re.search(r"```json\n(.*?)```", gemini_raw_response, re.DOTALL)
            if json_match:
                json_str = json_match.group(1).strip()
            else:
                json_str = gemini_raw_response.strip()

            try:
                parsed_data = json.loads(json_str)
                if "description" in parsed_data and "test_cases" in parsed_data:
                    print("Successfully parsed challenge from natural language input.")
                    return parsed_data
                else:
                    print(f"Warning: Parsed JSON is missing 'description' or 'test_cases' keys during parsing. Retrying.")
            except json.JSONDecodeError as e:
                print(f"Warning: Failed to decode JSON from Gemini's response during parsing: {e}. Raw response: {json_str}. Retrying.")
        else:
            print("Warning: Gemini API returned no response for parsing. Retrying.")
        time.sleep(base_delay * (2 ** attempt))

    print("Error: Could not parse human-made challenge input after several attempts.")
    return None
