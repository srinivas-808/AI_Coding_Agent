# backend/app.py
from flask import Flask, request, jsonify, render_template
import os
import sys
import json
import threading
import time

# Add the backend directory to the Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__))))

# Now import your agent's core logic and parsing functions
from agent_core import solve_challenge_core, parse_human_challenge_input_with_gemini, get_challenge_hash, load_solved_challenge, SOLVED_CHALLENGES_DIR

app = Flask(__name__,
            static_folder='static',
            template_folder='templates')

# A simple in-memory store for ongoing challenges.
ongoing_challenges = {}
challenge_id_counter = 0
challenge_id_lock = threading.Lock()

def generate_challenge_id():
    global challenge_id_counter
    with challenge_id_lock:
        challenge_id_counter += 1
        return f"challenge_{challenge_id_counter}"

@app.route('/')
def index():
    """Serves the main HTML page."""
    return render_template('index.html')

@app.route('/submit_challenge', methods=['POST'])
def submit_challenge():
    data = request.json
    if not data:
        return jsonify({"error": "Invalid JSON payload"}), 400

    challenge_desc = data.get("description")
    test_cases = data.get("test_cases")
    raw_input = data.get("raw_input")
    max_attempts = data.get("max_attempts", 5)

    parsed_challenge_data = {}

    if raw_input:
        print(f"Received raw input for parsing: {raw_input[:100]}...")
        parsed_challenge_data = parse_human_challenge_input_with_gemini(raw_input)
        if not parsed_challenge_data:
            return jsonify({"error": "Failed to parse natural language input using AI."}), 500
        challenge_desc = parsed_challenge_data.get("description")
        test_cases = parsed_challenge_data.get("test_cases")
    elif not challenge_desc or not test_cases:
        return jsonify({"error": "Missing 'description' or 'test_cases' in payload."}), 400

    challenge_hash = get_challenge_hash(challenge_desc, test_cases)
    existing_solution = load_solved_challenge(challenge_hash)

    if existing_solution:
        return jsonify({
            "challenge_id": f"cached_{challenge_hash}", # Use a distinct ID for cached solutions
            "challenge_hash": challenge_hash,
            "status": "solved",
            "message": "Challenge already solved and loaded from cache.",
            "solution": {
                "final_code": existing_solution['final_code'],
                "attempts_taken": existing_solution['attempts_taken'],
                "solved_timestamp": existing_solution['solved_timestamp']
            }
        }), 200

    current_challenge_id = generate_challenge_id()
    ongoing_challenges[current_challenge_id] = {
        "status": "pending",
        "description": challenge_desc,
        "test_cases": test_cases,
        "challenge_hash": challenge_hash,
        "max_attempts": max_attempts,
        "result": None
    }

    def run_solver_task(challenge_id_to_track, desc, tc, attempts):
        print(f"Starting solver task for {challenge_id_to_track}...")
        try:
            result = solve_challenge_core(desc, tc, attempts)
            ongoing_challenges[challenge_id_to_track]["result"] = result
            ongoing_challenges[challenge_id_to_track]["status"] = result["status"]
            print(f"Solver task for {challenge_id_to_track} finished with status: {result['status']}")
        except Exception as e:
            print(f"Error in solver task {challenge_id_to_track}: {e}")
            ongoing_challenges[challenge_id_to_track]["status"] = "error"
            ongoing_challenges[challenge_id_to_track]["result"] = {"status": "error", "message": str(e)}

    thread = threading.Thread(target=run_solver_task, args=(current_challenge_id, challenge_desc, test_cases, max_attempts))
    thread.start()

    return jsonify({
        "challenge_id": current_challenge_id,
        "challenge_hash": challenge_hash,
        "status": "processing",
        "message": "Challenge submitted for processing. Use /challenge_status to check."
    }), 202

@app.route('/challenge_status/<challenge_id>', methods=['GET'])
def get_challenge_status(challenge_id):
    challenge_info = ongoing_challenges.get(challenge_id)
    if not challenge_info:
        # Check if it's a cached solution ID
        if challenge_id.startswith("cached_"):
            challenge_hash = challenge_id.replace("cached_", "")
            existing_solution = load_solved_challenge(challenge_hash)
            if existing_solution:
                return jsonify({
                    "challenge_id": challenge_id,
                    "challenge_hash": challenge_hash,
                    "status": "solved",
                    "message": "Challenge already solved and loaded from cache.",
                    "solution": {
                        "final_code": existing_solution['final_code'],
                        "attempts_taken": existing_solution['attempts_taken'],
                        "solved_timestamp": existing_solution['solved_timestamp']
                    }
                }), 200
        return jsonify({"error": "Challenge ID not found or expired."}), 404

    return jsonify(challenge_info), 200

@app.route('/solved_challenges', methods=['GET'])
def get_all_solved_challenges():
    solved_list = []
    for filename in os.listdir(SOLVED_CHALLENGES_DIR):
        if filename.endswith(".json"):
            file_path = os.path.join(SOLVED_CHALLENGES_DIR, filename)
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    solved_list.append(data)
            except json.JSONDecodeError:
                print(f"Warning: Could not parse {filename} in solved_challenges.")
            except Exception as e:
                print(f"Error reading {filename}: {e}")
    return jsonify(solved_list), 200


if __name__ == '__main__':
    print("Starting Flask Backend for AI Coding Agent...")
    print(f"Solved challenges directory: {os.path.abspath(SOLVED_CHALLENGES_DIR)}")
    app.run(debug=True, port=5000)
