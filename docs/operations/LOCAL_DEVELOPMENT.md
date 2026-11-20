# Local Development Commands

## API
```powershell
cd apps\api
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -e ".[dev]"
pytest
ruff check .
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

## Web
```powershell
cd apps\web
npm install
npm run lint
npm run typecheck
npm run build
npm run dev
```

## Widget
```powershell
cd apps\widget
npm install
npm run build
```

## Docker
At repository root, after creating `.env`:
```powershell
docker compose config
docker compose build
docker compose up
docker compose down
```
