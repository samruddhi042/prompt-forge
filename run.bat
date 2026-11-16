@echo off
if not exist venv (python -m venv venv)
call venv\Scripts\activate
pip install -q -r requirements.txt
if not exist .env copy .env.example .env
start http://localhost:8000
uvicorn backend.main:app --port 8000
