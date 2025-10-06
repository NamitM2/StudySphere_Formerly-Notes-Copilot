# cleanup.py
# Path: cleanup.py
import os

files_to_delete = ["chunks.db", "faiss_index.bin"]

print("--- Starting cleanup ---")
for filename in files_to_delete:
    if os.path.exists(filename):
        try:
            os.remove(filename)
            print(f"Successfully deleted {filename}")
        except OSError as e:
            print(f"Error deleting {filename}: {e}")
    else:
        print(f"{filename} not found, skipping.")
print("--- Cleanup complete ---")
