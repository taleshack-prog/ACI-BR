#!/bin/bash
cd "$(dirname "$0")/backend"
source venv/bin/activate
fuser -k 8001/tcp 2>/dev/null
sleep 1
uvicorn app.main:app --reload --port 8001
