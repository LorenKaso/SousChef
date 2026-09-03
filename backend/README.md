# SousChef - Setup & Running Instructions

## System Requirements
- Python 3.11 or higher
- Node.js 18 or higher
- npm
- Free memory: at least 8GB (for running models)

---

## Installation

### 1. Set up Python environment and install dependencies
```bash
cd backend
python -m venv .venv
.venv\Scripts\activate  # Windows
# or: source .venv/bin/activate  # Linux/Mac
pip install -r requirements.txt
```

### 2. Install Frontend dependencies
```bash
cd ../frontend
npm install
```

---

## Environment Variables (required for LLM layer)

Create a `.env` file in the `backend` directory with the following content:

```
GEMINI_API_KEY=your_api_key_here
GEMINI_MODEL=gemini-2.0-flash
HF_TOKEN=your_huggingface_token_here
HF_TTS_MODEL_HE=facebook/mms-tts-heb
HF_TTS_MODEL_EN=hexgrad/Kokoro-82M
```

- The Gemini API key can be obtained from Google AI Studio.
- Without this key, the LLM layer will not function (the system will only handle basic navigation commands).
- The HuggingFace token is required for TTS model downloads.

---

## Running

### Backend:
```bash
cd backend
.venv\Scripts\activate
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

### Frontend:
In a new terminal window:
```bash
cd frontend
npm run dev
```

- Frontend will be available at: http://localhost:5173
- Backend will listen at: http://localhost:8000
- API docs (Swagger): http://localhost:8000/docs

---

## Docker (optional)

You can run the backend with Docker:
```bash
docker-compose up --build
```

Note: the frontend must still be run separately with `npm run dev`.

---

## Important Notes
- Without `GEMINI_API_KEY` the system will only handle simple navigation commands (next, back, what now, etc.).
- Hebrew is supported but less accurate than English, particularly for speech recognition.
- Recommended to run on a machine with sufficient free memory — TTS and embedding models consume significant resources.
- Any changes to models or API keys should be updated in the `.env` file.

---

## Troubleshooting
- If the LLM fails to respond, check that the `GEMINI_API_KEY` is valid.
- Speech recognition issues? Use Chrome or Edge — the Web Speech API is required.
- Hebrew speech recognition may be unreliable depending on network connectivity to Google's servers.
- Unit conversion issues? Verify the ingredient exists in `conversions_bilingual.json`.