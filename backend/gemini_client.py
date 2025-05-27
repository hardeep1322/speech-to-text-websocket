import google.generativeai as genai
import os

# Replace with your actual Gemini API key
# WARNING: Hardcoding API keys is not recommended for production environments.
# Consider using environment variables or a secrets management system for better security.
API_KEY = "AIzaSyBjCQxKqnvJycXKmZbaZHjr6S8wozt2JCo"

def get_gemini_client():
    # Check for API key in environment variable
    # api_key = os.getenv("GOOGLE_API_KEY")
    # if not api_key:
    #     raise ValueError("GOOGLE_API_KEY environment variable not set")
    
    genai.configure(api_key=API_KEY)
    # Using 'gemini-1.5-flash-latest' as the model name for "Gemini 2.0 Flash-Lite"
    # You may need to verify the exact model name using the Google Cloud console or API
    return genai.GenerativeModel('gemini-1.5-flash-latest')

def generate_summary(text):
    try:
        model = get_gemini_client()
        prompt = f"""Please provide a concise summary of the following text. Focus on the main points and key information:

{text}

Summary:"""
        
        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        print(f"Error generating summary: {str(e)}")
        return "Error generating summary" 