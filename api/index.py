"""
Vercel serverless function entry point for FastAPI application.
This file is required for Vercel to properly route requests to your FastAPI app.
"""
import sys
import os
from pathlib import Path

# Get the project root directory (parent of api directory)
current_file = Path(__file__).resolve()
project_root = current_file.parent.parent
backend_dir = project_root / 'backend'

# Add both project root and backend directory to Python path
project_root_str = str(project_root)
backend_dir_str = str(backend_dir)

if project_root_str not in sys.path:
    sys.path.insert(0, project_root_str)
if backend_dir_str not in sys.path:
    sys.path.insert(0, backend_dir_str)

# Debug: Print paths for troubleshooting (will appear in Vercel logs)
# Uncomment if needed for debugging:
# print(f"Current file: {current_file}")
# print(f"Project root: {project_root}")
# print(f"Python path: {sys.path}")

# Import the FastAPI app
try:
    from backend.main import app
except ImportError as e:
    # Provide more detailed error information
    import traceback
    error_msg = f"""
    Failed to import backend.main:
    Error: {str(e)}
    Current file: {current_file}
    Project root: {project_root}
    Project root exists: {os.path.exists(project_root)}
    Backend path: {project_root / 'backend'}
    Backend exists: {os.path.exists(project_root / 'backend')}
    Main.py exists: {os.path.exists(project_root / 'backend' / 'main.py')}
    Python path: {sys.path}
    Traceback:
    {traceback.format_exc()}
    """
    raise ImportError(error_msg) from e

# Export the app for Vercel's serverless function handler
# Vercel will automatically detect and use this as the handler
__all__ = ["app"]