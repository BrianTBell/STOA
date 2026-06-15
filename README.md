# STOA
 
A research tool and emergent knowledge graph. Upload a technical paper and STOA parses it, stores it as a node in a graph database, and surfaces the most similar existing papers to guide your reading across a new field.
 
**Full writeup and demo:** https://briantbell.github.io/stoa.html
 
## How it works
 
1. Upload a paper (local PDF or arXiv ID).
2. Claude screens it, then extracts core concepts, methods, and metadata.
3. The paper text is embedded with `sentence-transformers` and discarded (the graph stays copyright clean, holding only summaries, embeddings, and a link back).
4. The paper is written to Neo4j as a node, with the embedding stored as a queryable vector.
5. Cosine similarity nominates each paper's top neighbors, building the `SIMILAR_TO` edges.
6. A React + Sigma.js frontend renders the graph as an explorable atlas.
## Stack
 
Python, FastAPI, Uvicorn, Neo4j (vector index), `sentence-transformers`, the Claude API, and React + TypeScript + Vite + Sigma.js.
 
See `ARCHITECTURE.md` for the full pipeline and design notes, `SCHEMA.md` for the node schema, and `ROADMAP.md` for the phased build plan.
 
## Setup
 
Install dependencies:
 
```powershell
python -m pip install -r requirements.txt
```
 
Copy `.env.example` to `.env` and fill in your Claude and Neo4j settings.
 
Launch the full app (API + frontend) from the repo root:
 
```powershell
python -m backend.dev launch
```
 
`reboot` restarts both and `shutdown` stops them. Use `python -m backend.dev status` to check state. Then open `http://127.0.0.1:5173` and use **Add paper** to ingest a PDF or arXiv ID.
 
To run the API alone, see its docs at `http://127.0.0.1:8000/docs`:
 
```powershell
python -m backend.api
```
 
## Tests
 
```powershell
python -m unittest discover -s backend\tests -v
```
