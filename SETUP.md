# Backend Setup

## Prerequisites
- Python 3.11
- Node.js >=20 (the frontend dependencies require it — check with `node --version`)
- An OpenAI API key

---

## First-time setup

```bash
cd Earthquake
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Create a `.env` file in the `Earthquake/` directory:

```
OPENAI_KEY=sk-...
LANGSMITH_API_KEY=lsv... (not required to run)
```

---

## Running the server

```bash
cd Earthquake
source .venv/bin/activate
langgraph dev
```

The API is now available at **http://localhost:2024**.

---

## Frontend setup

```bash
cd frontend
npm install
npm run dev
```

The app is now available at **http://localhost:5173**.

> The backend must be running on port 2024 before using the frontend.
