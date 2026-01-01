"""
Vercel serverless function entry point for FastAPI application.
This file is required for Vercel to properly route requests to your FastAPI app.
"""
import sys
import os

# Add the backend directory to the Python path
backend_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backend")
sys.path.insert(0, backend_path)

from main import app

# Export the app for Vercel's serverless function handler
# Vercel will automatically detect and use this as the handler
__all__ = ["app"]

