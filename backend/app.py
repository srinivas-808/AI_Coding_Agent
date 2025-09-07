# backend/app.py
from flask import Flask, request, jsonify, render_template, send_from_directory
import os
import sys

# Add the parent directory to the path to find agent_core and its submodules
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from agent_core import submit_challenge, parse_human_challenge_input_with_gemini, challenge_store, load_solved_challenge, SOLVED_CHALLENGES_DIR

app = Flask(__name__,
            static_folder='static',
            template_folder='templates')


@app.route('/')
def serve_index():
    return render_template('index.html')


@app.route('/static/<path:filename>')
def serve_static(filename):
    return send_from_directory(app.static_folder, filename)


@app.route('/submit_challenge', methods=['POST'])
def handle_submit_challenge():
    data = request.json
    raw_input = data.get('raw_input')
    max_attempts = data.get('max_attempts', 5)

    if raw_input:
        parsed_data = parse_human_challenge_input_with_gemini(raw_input)
        if parsed_data:
            parsed_data['max_attempts'] = max_attempts
            challenge_id = submit_challenge(parsed_data)
            return jsonify({
                "message": "Challenge submitted for processing.",
                "challenge_id": challenge_id,
                "status": "submitted"
            }), 202
        else:
            return jsonify({"error": "Failed to parse natural language input."}), 400
    else:
        description = data.get('description')
        test_cases = data.get('test_cases', [])
        if not description or not test_cases:
            return jsonify({"error": "Description and test_cases are required."}), 400

        challenge_id = submit_challenge(data)
        return jsonify({
            "message": "Challenge submitted for processing.",
            "challenge_id": challenge_id,
            "status": "submitted"
        }), 202


@app.route('/challenge_status/<challenge_id>')
def get_challenge_status(challenge_id):
    challenge = challenge_store.get(challenge_id)
    if challenge:
        # Load code from result if available
        if challenge['result'] and challenge['result'].get('final_code') and not challenge['result'].get('error_details'):
            # This is a solved challenge.
            challenge['solution'] = {'final_code': challenge['result']['final_code']}
            del challenge['result']['final_code'] # Remove the code from the result to avoid redundancy
        return jsonify(challenge), 200
    else:
        return jsonify({"error": "Challenge not found."}), 404


@app.route('/solved_challenges')
def get_solved_challenges():
    solved_challenges_list = []
    if os.path.exists(SOLVED_CHALLENGES_DIR):
        for filename in os.listdir(SOLVED_CHALLENGES_DIR):
            if filename.endswith('.json'):
                challenge_hash = filename.replace('.json', '')
                challenge_data = load_solved_challenge(challenge_hash)
                if challenge_data:
                    solved_challenges_list.append(challenge_data)
    return jsonify(solved_challenges_list)


if __name__ == '__main__':
    print("Starting Flask Backend for AI Coding Agent...")
    print(f"Solved challenges directory: {SOLVED_CHALLENGES_DIR}")
    app.run(host='0.0.0.0', port=8080)
