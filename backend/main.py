from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
import os
from dotenv import load_dotenv

from routers.extract import router as extract_router
from routers.fill import router as fill_router
from routers.ai_fill import router as ai_fill_router
from routers.chat import router as chat
from fastapi.responses import HTMLResponse
load_dotenv()

app = FastAPI(
    title="JOBA Healthcare PDF Processor",
    description="PDF form field extraction and filling using direct coordinate-based approach",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(extract_router, prefix="/api/v1", tags=["extraction"])
app.include_router(fill_router, prefix="/api/v1", tags=["fill"])
app.include_router(ai_fill_router, prefix="/api/v1", tags=["ai-filling"])
app.include_router(chat,prefix="/chat/v1",tags=["chat"])

# @app.get("/")
# async def root():
#     return {"message": "JOBA Healthcare PDF Processor API", "status": "running"}

@app.get("/", response_class=HTMLResponse)
async def root():
    return """
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>JOBA AI Chat</title>
        <style>
            * {
                margin: 0;
                padding: 0;
                box-sizing: border-box;
            }
            body {
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, sans-serif;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                min-height: 100vh;
                display: flex;
                justify-content: center;
                align-items: center;
                padding: 20px;
            }
            .container {
                background: white;
                border-radius: 20px;
                box-shadow: 0 20px 60px rgba(0, 0, 0, 0.3);
                max-width: 600px;
                width: 100%;
                padding: 40px;
            }
            h1 {
                color: #333;
                margin-bottom: 30px;
                text-align: center;
                font-size: 28px;
            }
            .form-group {
                margin-bottom: 20px;
            }
            input[type="text"] {
                width: 100%;
                padding: 15px;
                border: 2px solid #e0e0e0;
                border-radius: 10px;
                font-size: 16px;
                transition: border-color 0.3s;
            }
            input[type="text"]:focus {
                outline: none;
                border-color: #667eea;
            }
            button {
                width: 100%;
                padding: 15px;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                color: white;
                border: none;
                border-radius: 10px;
                font-size: 16px;
                font-weight: 600;
                cursor: pointer;
                transition: transform 0.2s, box-shadow 0.2s;
            }
            button:hover {
                transform: translateY(-2px);
                box-shadow: 0 5px 15px rgba(102, 126, 234, 0.4);
            }
            button:active {
                transform: translateY(0);
            }
            button:disabled {
                opacity: 0.6;
                cursor: not-allowed;
                transform: none;
            }
            .response {
                margin-top: 30px;
                padding: 20px;
                background: #f5f5f5;
                border-radius: 10px;
                min-height: 50px;
                white-space: pre-wrap;
                word-wrap: break-word;
                display: none;
            }
            .response.show {
                display: block;
            }
            .loading {
                text-align: center;
                color: #667eea;
                font-style: italic;
            }
            .error {
                color: #e74c3c;
                background: #fee;
            }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>JOBA AI Chat</h1>
            <form id="chatForm">
                <div class="form-group">
                    <input 
                        type="text" 
                        id="userInput" 
                        placeholder="Type your message here..." 
                        required
                        autocomplete="off"
                    />
                </div>
                <button type="submit" id="submitBtn">Send</button>
            </form>
            <div id="response" class="response"></div>
        </div>
        <script>
            const form = document.getElementById('chatForm');
            const input = document.getElementById('userInput');
            const submitBtn = document.getElementById('submitBtn');
            const responseDiv = document.getElementById('response');

            form.addEventListener('submit', async (e) => {
                e.preventDefault();
                
                const userMessage = input.value.trim();
                if (!userMessage) return;

                // Disable form during request
                submitBtn.disabled = true;
                submitBtn.textContent = 'Sending...';
                responseDiv.className = 'response loading';
                responseDiv.textContent = 'Loading...';
                responseDiv.classList.add('show');

                try {
                    const response = await fetch('/chat/v1/', {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json',
                        },
                        body: JSON.stringify({ user_message: userMessage })
                    });

                    if (!response.ok) {
                        throw new Error('Failed to get response');
                    }

                    const data = await response.text();
                    responseDiv.className = 'response show';
                    responseDiv.textContent = data;
                    input.value = '';
                } catch (error) {
                    responseDiv.className = 'response error show';
                    responseDiv.textContent = 'Error: ' + error.message;
                } finally {
                    submitBtn.disabled = false;
                    submitBtn.textContent = 'Send';
                }
            });
        </script>
    </body>
    </html>
    """

@app.get("/health")
async def health_check():
    return {"status": "healthy"}

if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True
    )
