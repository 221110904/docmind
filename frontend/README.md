# DocMind frontend

React + TypeScript + Vite. Talks to the FastAPI backend in `../backend`.

## Run it

```powershell
cd frontend
npm install
copy .env.example .env     # only needed if the backend is not on http://127.0.0.1:8000
npm run dev                # http://localhost:5173
```

Start the backend first (`uvicorn app.main:app --reload` in `backend`, venv active).

## Scripts

| Command | What it does |
|---|---|
| `npm run dev` | Dev server with hot reload |
| `npm test` | Unit and component tests (Vitest) |
| `npm run typecheck` | TypeScript check |
| `npm run build` | Type check and production build into `dist/` |

## Layout

- `src/api.ts`: typed client for the backend; every request goes through here.
- `src/pipeline.ts`: upload, read, index, with step reporting.
- `src/citations.ts`: turns `[1]` marks in an answer into clickable citations.
- `src/components/`: Documents, Ask, Search screens.
- `src/styles.css`: all styling; colors and fonts are tokens at the top.
