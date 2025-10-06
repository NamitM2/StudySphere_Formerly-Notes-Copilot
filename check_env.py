# check_env.py
# Path: check_env.py
from dotenv import load_dotenv
import os

print("--- Running dotenv check ---")

# Try to load the .env file from the current directory
was_loaded = load_dotenv()
print(f"Was a .env file loaded? {was_loaded}")

# Try to get the environment variable
api_key = os.getenv("GOOGLE_API_KEY")

print(f"The value for GOOGLE_API_KEY is: {api_key}")
print("--- Check complete ---")
