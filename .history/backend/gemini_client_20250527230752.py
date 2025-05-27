import google.generativeai as genai
import os

def get_gemini_client():
    # Check for API key in environment variable
    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        raise ValueError("GOOGLE_API_KEY environment variable not set")
    
    genai.configure(api_key=api_key)
    return genai.GenerativeModel('gemini-pro')

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