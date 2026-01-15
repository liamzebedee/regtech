# Agent Operations

## Running the Application

### Root Project (Analysis & Types)
```bash
cd /home/liam/Documents/projects/law
npm test          # Run all tests (47 passing)
npm run build     # Compile TypeScript
```

### Website (Next.js)
```bash
cd /home/liam/Documents/projects/law/app
npm run dev       # Start dev server
npm run build     # Production build
npm start         # Start production server
```

### Analysis Pipeline
```bash
python analysis/scripts/index_corpus.py    # Index corpus into database
python analysis/scripts/analyze_legislation.py --limit 10  # Analyze legislation
```

## Database Location
- SQLite database: `data/legislation.db`
- Corpus: `data/corpus/corpus.jsonl` (8.8GB)

## Key Dependencies
- Root: TypeScript 5.7, Vitest 3.0, better-sqlite3
- App: Next.js 15, React 19, Tailwind CSS 4
