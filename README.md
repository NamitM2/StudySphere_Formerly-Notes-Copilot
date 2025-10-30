# StudySphere

## Overview

StudySphere is an intelligent document analysis and learning platform that helps you extract insights from your personal document library using AI. Upload your PDFs, markdown files, and text documents, then ask questions in natural language to get accurate, source-backed answers drawn directly from your content.

The system goes beyond simple keyword search by understanding the semantic meaning of your questions and matching them against your documents using advanced embedding techniques. When your documents contain relevant information, you'll receive answers with clear citations. When they don't, the system transparently supplements with general knowledge from its language model, clearly indicating the source of each part of the answer.

Perfect for researchers, students, professionals, and anyone who needs to quickly find and synthesize information across large document collections. Features include multimodal document understanding (text + images), visual content analysis, and an intelligent Assignment IDE with AI-powered writing assistance.

## Technical Description

StudySphere is a full-stack web application built with modern technologies and deployed as a scalable system.

### Architecture

**Frontend (React + Vite)**
- Single-page application built with React 18 and Vite for fast development and optimized production builds
- Real-time UI updates with React hooks for state management
- Drag-and-drop file upload interface with visual feedback
- Tailwind CSS for responsive, gradient-themed dark/light mode design
- Client-side authentication state management with localStorage persistence
- Toast notification system for user feedback

**Backend (FastAPI + Python)**
- RESTful API built with FastAPI for high-performance async request handling
- JWT-based authentication using Supabase Auth for secure user sessions
- CORS middleware configured for cross-origin requests from the frontend
- File upload endpoint with content-type validation and size limits (200MB max)
- Question-answering endpoint with dynamic chunk retrieval and answer synthesis

**Database (Supabase/PostgreSQL)**
- PostgreSQL database for storing user accounts, documents metadata, and text chunks
- Vector storage for document embeddings using pgvector extension
- Row-level security policies ensuring users only access their own documents
- Automated timestamp tracking for document creation and modification

**Document Processing Pipeline**
1. File ingestion supports PDF (via PyPDF and PyMuPDF), Markdown, and plain text formats
2. Text extraction and chunking with configurable overlap (360 chars for PDFs, 900 chars default with 150 char overlap) for context preservation
3. Embedding generation using Google's Generative AI models (text-embedding-004)
4. Chunk storage in PostgreSQL with associated metadata (filename, page numbers, user_id)

**Retrieval and Answer Generation**
1. Query embedding: User questions are converted to 768-dimensional vector embeddings
2. Dynamic k-selection: Retrieves variable numbers of chunks (up to 30) based on similarity scores
3. Similarity threshold filtering: Uses 0.80 similarity threshold (max cosine distance of 0.40) to filter relevant chunks
4. Maximal Marginal Relevance (MMR): Reduces redundancy by selecting diverse, relevant chunks
5. Lexical scoring: Combines semantic similarity with keyword overlap for improved ranking
6. Answer synthesis: Google Gemini 2.5 Flash generates answers from retrieved context
7. Mode detection: Automatically tags answers as "From Notes", "Model Knowledge", or "Mixed" based on content analysis
8. Citation extraction: Identifies which documents contributed to the answer with source filenames

**Deployment**
- Backend runs on Uvicorn ASGI server with hot-reload in development
- Frontend served via Vite dev server locally, optimized static build for production
- Development runner script (dev.py) orchestrates both services with proper environment configuration
- Environment variables manage API keys, database connections, and CORS origins
- Question history tracking with user-specific query logs and citation references
- Multi-key API failover system supporting up to 5 backup Google AI API keys for improved reliability

**Key Technologies**
- Python: FastAPI, Uvicorn, PyPDF, PyMuPDF, NumPy, Supabase client, Google Generative AI, python-jose
- JavaScript: React 18, Vite, Tailwind CSS
- Database: PostgreSQL with pgvector extension
- Authentication: Supabase Auth with JWT tokens
- AI/ML: Google Gemini 2.5 Flash for answer generation, text-embedding-004 for semantic search (768-dim)

## Feel free to use in any way you would like to :)
