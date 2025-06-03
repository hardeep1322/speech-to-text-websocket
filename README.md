# AI Interview Assistant

A real-time interview assistant that uses speech-to-text and AI to provide interview feedback and summaries.

## Security Considerations

1. **API Key Authentication**
   - All WebSocket connections require a valid API key
   - API key should be set as an environment variable `API_KEY`
   - Never commit API keys or credentials to the repository

2. **Google Cloud Credentials**
   - Store Google Cloud credentials securely
   - Use environment variables or secure secret management
   - Never commit credentials to the repository

3. **CORS Configuration**
   - Only allowed origins can access the API
   - Production domains must be explicitly added to the allowed origins list

## Setup Instructions

### Backend Setup

1. Install Python dependencies:
   ```bash
   cd backend
   pip install -r requirements.txt
   ```

2. Set up environment variables:
   ```bash
   export API_KEY="your-secure-api-key"
   export GOOGLE_APPLICATION_CREDENTIALS="path/to/your/credentials.json"
   ```

3. Run the backend server:
   ```bash
   uvicorn main:app --host 0.0.0.0 --port 8000
   ```

### Frontend Setup

1. Install Node.js dependencies:
   ```bash
   cd frontend
   npm install
   ```

2. Set up environment variables:
   Create a `.env` file with:
   ```
   VITE_API_URL=your_backend_url
   VITE_API_KEY=your_api_key
   ```

3. Run the development server:
   ```bash
   npm run dev
   ```

## Deployment

### Backend (Render)
1. Create a new Web Service on Render
2. Connect your GitHub repository
3. Set environment variables:
   - `API_KEY`
   - `GOOGLE_APPLICATION_CREDENTIALS` (as a JSON string)
4. Deploy

### Frontend (Vercel)
1. Create a new project on Vercel
2. Connect your GitHub repository
3. Set environment variables:
   - `VITE_API_URL`
   - `VITE_API_KEY`
4. Deploy

## Development

- Backend runs on port 8000
- Frontend development server runs on port 5173
- WebSocket connections require API key authentication
- All API endpoints are protected with security headers