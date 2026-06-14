# STOA
A community curated knowledge web.

I find research to be difficult. In part, its because I struggle to get a lay of the land. As with anything, when I emmerse myself, the charcters, concepts, and and ties between them become clearer. I guess I could say that at first, I dont know what I dont know, and that's tough.

Not long ago, I had the pleasure of being able to walk up to my professors to ask, "Hey, who knows about ___", and right away, "Go talk to Ted next door". Talking to, Ted, next door, I could get that lay of the land, what the field is, who's working it, what book to start with and what papers to read. Each of these, "Teds next door", has a ton of good advice, all of which was curated through their own technical review as a reearching in that field.

The only problem I have with this is that you have to know a guy who knows a guy. And well before all of that you jump through hoops to get accepted into the community. Worst of all, you may exit the community for one reason or another, like me. This applies to everyone involved. Wonderful collections of people and knowledge are not easily accessible. Its not always as simple as walking up to someones door. 

One funny thing is that people have, and will continue ask the same questions, and they'll be referenced door to door just like I was. In doing this, they'll develop their own understanding of the community, and eventually some knowledge in a techincal domain to the same depth as the professors I so fondly bothered. I think collectively we spend a lot of time doing this. That's not a bad thing, but having bowed out of the community, Its odd to my that many spend so much time understanding an entire community that I no longer have direct access to. The answers I want are there, but I dont have access, and I could be directing someone there now, but again, I'm not there. 

I think it would be nice to have a tool anyone can walk up to. It should point them in the right direction, tells you which texts to read and which are most relevant. What fields are closest to which. Essentially, the knoweldge map, but one like my old community, which grows, self organizes, and gets validated by the people who use it. I'll call it a living otology, to sound very clever and romantic.  

## Backend setup

Install the Python dependencies:

```powershell
python -m pip install -r requirements.txt
```

Copy `.env.example` to `.env` and provide the Claude and Neo4j settings. Then run the API:

```powershell
python -m backend.api
```

Open `http://127.0.0.1:8000/docs` for the interactive OpenAPI documentation.

## Frontend

Run the complete local application from the repository root:

```powershell
python -m backend.dev launch
python -m backend.dev reboot
python -m backend.dev shutdown
```

`launch` and `reboot` start the API and frontend in the background, wait for
both to become available, and open STOA in the default browser. Runtime logs
are stored under `backend/dev/.runtime/`. Use `python -m backend.dev status`
to check whether each process is running.

The individual startup commands remain available when debugging:

Start the backend in the first PowerShell window:

```powershell
python -m backend.api
```

In a second PowerShell window, install and start the frontend:

```powershell
cd frontend
npm install
npm run dev
```

Open `http://127.0.0.1:5173`. The Vite development server forwards `/api`
requests to the FastAPI server on port `8000`.

Use **Add paper** in the top-right corner to upload a local PDF or enter an
arXiv ID. When ingestion finishes, the atlas refreshes and focuses the new paper.

Build the production frontend:

```powershell
cd frontend
npm run build
```

## API examples

Upload a local PDF as the request body:

```powershell
curl.exe -X POST "http://127.0.0.1:8000/ingest/pdf?filename=paper.pdf" `
  -H "Content-Type: application/pdf" `
  --data-binary "@C:\path\to\paper.pdf"
```

Ingest an arXiv paper:

```powershell
curl.exe -X POST "http://127.0.0.1:8000/ingest/arxiv" `
  -H "Content-Type: application/json" `
  -d '{"arxiv_id":"2301.04567"}'
```

Query the graph:

```powershell
curl.exe "http://127.0.0.1:8000/papers"
curl.exe "http://127.0.0.1:8000/papers/localpdf:YOUR_PAPER_ID"
curl.exe "http://127.0.0.1:8000/papers/localpdf:YOUR_PAPER_ID/edges"
curl.exe "http://127.0.0.1:8000/papers/localpdf:YOUR_PAPER_ID/similar"
```

Run the automated API tests:

```powershell
python -m unittest discover -s backend\tests -v
```
