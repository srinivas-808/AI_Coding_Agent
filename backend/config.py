# ai_coding_agent/config.py
import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Get the Gemini API Key
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

if not GEMINI_API_KEY:
    print("Error: GEMINI_API_KEY not found in .env file or environment variables.")
    print("Please ensure you have a .env file with GEMINI_API_KEY=YOUR_API_KEY")
    exit(1)
