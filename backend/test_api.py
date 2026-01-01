#!/usr/bin/env python3
"""
Simple test script for the JOBA Healthcare PDF Processor
"""

import requests
import json
import os

# Configuration
BASE_URL = "http://localhost:8000/api/v1"

def test_api():
    """Test the API endpoints"""
    
    print("🧪 Testing JOBA Healthcare PDF Processor API...")
    
    # Test health endpoint
    try:
        response = requests.get(f"{BASE_URL}/test")
        if response.status_code == 200:
            print("✅ API is running and accessible")
        else:
            print("❌ API test endpoint failed")
            return False
    except requests.exceptions.ConnectionError:
        print("❌ Cannot connect to API. Make sure the server is running on http://localhost:8000")
        return False
    
    # Test PDF upload (you'll need to provide a test PDF)
    test_pdf_path = input("Enter path to a test PDF file (or press Enter to skip): ").strip()
    
    if test_pdf_path and os.path.exists(test_pdf_path):
        try:
            with open(test_pdf_path, 'rb') as f:
                files = {'file': (os.path.basename(test_pdf_path), f, 'application/pdf')}
                response = requests.post(f"{BASE_URL}/extract", files=files)
            
            if response.status_code == 200:
                result = response.json()
                print("✅ PDF processing successful!")
                print(f"📄 Filename: {result['filename']}")
                print(f"⏱️ Processing time: {result['processing_time']:.2f}s")
                print("📊 Extracted fields:")
                print(json.dumps(result['extracted_fields'], indent=2))
                print("🎯 Confidence scores:")
                print(json.dumps(result['confidence_scores'], indent=2))
            else:
                print(f"❌ PDF processing failed: {response.text}")
        except Exception as e:
            print(f"❌ Error testing PDF upload: {str(e)}")
    else:
        print("⏭️ Skipping PDF upload test")
    
    print("\n🎉 API testing completed!")
    return True

if __name__ == "__main__":
    test_api()
