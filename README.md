# JOBA Healthcare PDF Processor

A FastAPI-based backend service for extracting form fields from PDFs, AI-powered form filling, and generating filled PDF documents.

## Features

- 📄 **PDF Field Extraction** - Extract form fields with coordinates from PDF documents
- 🤖 **AI-Powered Form Filling** - Use Google Gemini AI to intelligently fill form fields based on user input
- ✍️ **PDF Form Filling** - Fill PDF forms with extracted or AI-generated data
- 💬 **AI Chat Interface** - Interactive chat interface powered by Gemini AI
- 🔄 **RESTful API** - Clean API endpoints for integration

## Installation

### Prerequisites

- Python 3.13+
- pip

### Setup

1. Clone the repository:
git clone <repository-url>
cd joba/backend2. Create and activate virtual environment:
python -m venv venv
# Windows
venv\Scripts\activate
# Linux/Mac
source venv/bin/activate3. Install dependencies:
pip install -r requirements.txt4. Create `.env` file in the backend directory:
GEMINI_API_KEY=your_gemini_api_key_here## Usage

### Start the Server

uvicorn main:app --reloadThe API will be available at `http://127.0.0.1:8000`

### API Documentation

- Swagger UI: `http://127.0.0.1:8000/docs`
- ReDoc: `http://127.0.0.1:8000/redoc`

## API Endpoints

### Extraction
- `POST /api/v1/extract` - Extract form fields from PDF
- `GET /api/v1/extract/test` - Test endpoint

### Form Filling
- `POST /api/v1/fill` - Receive form data
- `POST /api/v1/fill_pdf` - Fill PDF with form data (returns filled PDF)

### AI Services
- `POST /api/v1/ai-fill` - AI-powered form field filling
- `POST /chat/v1/` - AI chat endpoint

### Health Check
- `GET /health` - Health check endpoint
- `GET /` - Chat interface (HTML page)

## Workflow

1. **Extract**: Upload PDF → Get extracted fields with coordinates
2. **AI Fill**: Provide user input + extracted fields → Get AI-filled field values
3. **Fill PDF**: Upload original PDF + filled data → Download filled PDF

## Project Structure
