# ui/app.py

import streamlit as st
import requests

# --- CONFIGURATION ---
API_URL = "http://localhost:8000"
st.set_page_config(
    page_title="Notes Copilot", 
    page_icon="📝",
    layout="wide" # Use the full page width
)

# --- SIDEBAR ---
with st.sidebar:
    st.header("1. Add a Document")
    uploaded_file = st.file_uploader("Upload a PDF to the knowledge base", type="pdf")

    if st.button("Clear Index"):
        with st.spinner("Clearing index..."):
            try:
                requests.post(f"{API_URL}/v1/clear")
                st.success("Index cleared!")
                st.session_state.uploaded_file_name = None
            except requests.exceptions.RequestException as e:
                st.error(f"Error connecting to API: {e}")

# Initialize session state for tracking uploaded file
if "uploaded_file_name" not in st.session_state:
    st.session_state.uploaded_file_name = None

# Handle the file upload logic
if uploaded_file is not None:
    if uploaded_file.name != st.session_state.uploaded_file_name:
        with st.spinner('Reading, chunking, and embedding file...'):
            try:
                files = {'file': (uploaded_file.name, uploaded_file, uploaded_file.type)}
                response = requests.post(f"{API_URL}/v1/ingest", files=files)
                if response.status_code == 200:
                    st.session_state.uploaded_file_name = uploaded_file.name
                    st.success(f"Success! Document processed. Total vectors: {response.json()['vectors_in_index']}")
                else:
                    st.error(f"Error: {response.status_code} - {response.text}")
            except requests.exceptions.RequestException as e:
                st.error(f"Error connecting to API: {e}")

# --- MAIN PAGE ---
st.title("📝 Notes Copilot")
st.write("Welcome! This app helps you search and ask questions about your documents.")
st.divider()

st.header("2. Ask a Question")
query = st.text_input("Ask a question about your notes:", key="query_input")

if query:
    with st.spinner('Searching for the answer...'):
        try:
            response = requests.post(f"{API_URL}/v1/search", json={"query": query})
            if response.status_code == 200:
                answer = response.json().get("answer", "Sorry, I couldn't formulate an answer.")
                st.subheader("Answer:")
                st.markdown(answer)
            else:
                st.error(f"Error: {response.status_code} - {response.text}")
        except requests.exceptions.RequestException as e:
            st.error(f"Error connecting to API: {e}")