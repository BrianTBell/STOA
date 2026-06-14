import { useEffect, useRef, useState } from "react";

import AboutPage from "./AboutPage";
import { colorForDomain, normalizedDomain, primaryConcept } from "./atlas";
import GraphCanvas from "./GraphCanvas";
import stoaLogo from "./stoa-logo.png";
import type { GraphPayload, Paper } from "./types";

type LoadState =
  | { status: "loading" }
  | { status: "ready"; payload: GraphPayload }
  | { status: "error"; message: string };

type IngestState =
  | { status: "idle" }
  | { status: "working"; message: string }
  | { status: "error"; message: string };

type IngestionResponse = {
  paper: Paper;
  similarity_edges: unknown[];
};

type UploadNotice = {
  kind: "success" | "duplicate" | "error";
  title: string;
  message: string;
};

type ApiErrorDetail = {
  code?: string;
  message?: string;
  rationale?: string;
  paper?: Paper;
};

type SelectedRegion = {
  label: string;
  kind: "domain" | "concept";
};

function formatDate(value: string | null): string {
  if (!value) return "Date not available";
  const date = new Date(value);
  return Number.isNaN(date.getTime())
    ? value
    : new Intl.DateTimeFormat("en", {
        year: "numeric",
        month: "short",
        day: "numeric",
      }).format(date);
}

export default function App() {
  const path = window.location.pathname.replace(/\/+$/, "") || "/";
  return path === "/about" ? <AboutRoute /> : <AtlasApp />;
}

function AboutRoute() {
  return (
    <main className="app-shell about-shell">
      <div className="star-field" aria-hidden="true" />
      <header className="masthead">
        <div className="brand-lockup">
          <img className="brand-logo" src={stoaLogo} alt="STOA logo" />
          <div>
            <p className="eyebrow">Living knowledge atlas</p>
            <h1>STOA</h1>
          </div>
        </div>
        <div className="masthead-actions">
          <a className="about-button is-active" href="/">
            Atlas
          </a>
        </div>
      </header>
      <AboutPage onReturn={() => window.location.assign("/")} />
    </main>
  );
}

function AtlasApp() {
  const [loadState, setLoadState] = useState<LoadState>({ status: "loading" });
  const [selectedPaper, setSelectedPaper] = useState<Paper | null>(null);
  const [search, setSearch] = useState("");
  const [focusId, setFocusId] = useState<string | null>(null);
  const [regionNote, setRegionNote] = useState<SelectedRegion | null>(null);
  const [showIngest, setShowIngest] = useState(false);
  const [ingestMode, setIngestMode] = useState<"pdf" | "arxiv">("pdf");
  const [arxivId, setArxivId] = useState("");
  const [ingestState, setIngestState] = useState<IngestState>({
    status: "idle",
  });
  const [uploadNotice, setUploadNotice] = useState<UploadNotice | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  async function loadGraph(signal?: AbortSignal): Promise<GraphPayload> {
    const response = await fetch("/api/graph?limit=5000", { signal });
    if (!response.ok) {
      throw new Error(`The atlas API returned ${response.status}.`);
    }
    const payload = (await response.json()) as GraphPayload;
    setLoadState({ status: "ready", payload });
    return payload;
  }

  useEffect(() => {
    const controller = new AbortController();
    loadGraph(controller.signal).catch((error: unknown) => {
      if (error instanceof DOMException && error.name === "AbortError") return;
      setLoadState({
        status: "error",
        message:
          error instanceof Error ? error.message : "The atlas could not be loaded.",
      });
    });
    return () => controller.abort();
  }, []);

  const payload = loadState.status === "ready" ? loadState.payload : null;
  const domains = payload
    ? [...new Set(payload.papers.map(normalizedDomain))].sort()
    : [];
  const normalizedSearch = search.trim().toLowerCase();
  const searchResults =
    payload && normalizedSearch
      ? payload.papers
          .filter((paper) =>
            [
              paper.title,
              paper.domain,
              ...paper.authors,
              ...paper.concepts,
              ...paper.methods,
            ]
              .filter(Boolean)
              .some((value) => value!.toLowerCase().includes(normalizedSearch)),
          )
          .slice(0, 7)
      : [];

  function selectSearchResult(paper: Paper) {
    setSelectedPaper(paper);
    setFocusId(paper.id);
    setSearch("");
    setRegionNote(null);
  }

  function focusDomain(domain: string) {
    setSelectedPaper(null);
    setFocusId(`domain::${domain}`);
    setRegionNote({ label: domain, kind: "domain" });
  }

  async function submitIngestion(body: BodyInit, endpoint: string) {
    let specificErrorHandled = false;
    setUploadNotice(null);
    setIngestState({
      status: "working",
      message: "Reading, screening, and mapping the paper...",
    });
    try {
      const response = await fetch(endpoint, {
        method: "POST",
        body,
        headers:
          typeof body === "string"
            ? { "Content-Type": "application/json" }
            : { "Content-Type": "application/pdf" },
      });
      if (!response.ok) {
        const responseBody = (await response.json().catch(() => null)) as {
          detail?: ApiErrorDetail | string;
        } | null;
        const detail =
          responseBody?.detail && typeof responseBody.detail === "object"
            ? responseBody.detail
            : null;
        const fallbackMessage =
          typeof responseBody?.detail === "string"
            ? responseBody.detail
            : `Ingestion failed with status ${response.status}.`;

        if (detail?.code === "duplicate_paper" && detail.paper) {
          setSelectedPaper(detail.paper);
          setFocusId(detail.paper.id);
          setShowIngest(false);
          setIngestState({ status: "idle" });
          setUploadNotice({
            kind: "duplicate",
            title: "Paper already in STOA",
            message:
              detail.message ||
              `${detail.paper.title || "This paper"} is already mapped.`,
          });
          if (fileInputRef.current) fileInputRef.current.value = "";
          return;
        }

        const notice =
          detail?.code === "not_academic_paper"
            ? {
                title: "Not accepted as an academic paper",
                message:
                  detail.rationale ||
                  detail.message ||
                  "The intake screen rejected this upload.",
              }
            : detail?.code === "cannot_read_paper"
              ? {
                  title: "Could not read the paper",
                  message:
                    detail.message ||
                    "The PDF may be scanned, corrupted, or contain no extractable text.",
                }
              : {
                  title: "Paper ingestion failed",
                  message: detail?.message || fallbackMessage,
                };
        setUploadNotice({ kind: "error", ...notice });
        specificErrorHandled = true;
        throw new Error(notice.message);
      }
      const result = (await response.json()) as IngestionResponse;
      const refreshed = await loadGraph();
      const paper =
        refreshed.papers.find((candidate) => candidate.id === result.paper.id) ||
        result.paper;
      setSelectedPaper(paper);
      setFocusId(paper.id);
      setShowIngest(false);
      setArxivId("");
      setIngestState({ status: "idle" });
      setUploadNotice({
        kind: "success",
        title: "Paper added to STOA",
        message: `"${paper.title || "Untitled paper"}" completed screening, extraction, vocabulary resolution, embedding, storage, and ${result.similarity_edges.length} similarity connection${result.similarity_edges.length === 1 ? "" : "s"}.`,
      });
      if (fileInputRef.current) fileInputRef.current.value = "";
    } catch (error) {
      setIngestState({
        status: "error",
        message: error instanceof Error ? error.message : "Ingestion failed.",
      });
      if (!specificErrorHandled) {
        setUploadNotice({
          kind: "error",
          title: "Paper ingestion failed",
          message: error instanceof Error ? error.message : "Ingestion failed.",
        });
      }
    }
  }

  function ingestPdf(file: File | undefined) {
    if (!file) return;
    void submitIngestion(
      file,
      `/api/ingest/pdf?filename=${encodeURIComponent(file.name)}`,
    );
  }

  function ingestArxiv() {
    const cleanId = arxivId.trim();
    if (!cleanId) return;
    void submitIngestion(JSON.stringify({ arxiv_id: cleanId }), "/api/ingest/arxiv");
  }

  const hasWebSource =
    selectedPaper &&
    (selectedPaper.source_url.startsWith("https://") ||
      selectedPaper.source_url.startsWith("http://"));
  const sourceHref = selectedPaper
    ? hasWebSource
      ? selectedPaper.source_url
      : `https://scholar.google.com/scholar?q=${encodeURIComponent(
          [selectedPaper.title, selectedPaper.authors[0]].filter(Boolean).join(" "),
        )}`
    : "";

  return (
    <main className={`app-shell ${selectedPaper ? "has-selection" : ""}`}>
      <div className="star-field" aria-hidden="true" />

      <header className="masthead atlas-masthead">
        <div className="brand-lockup">
          <img className="brand-logo" src={stoaLogo} alt="STOA logo" />
          <div>
            <p className="eyebrow">Living knowledge atlas</p>
            <h1>STOA</h1>
          </div>
        </div>
        <section className="search-zone">
          <label htmlFor="atlas-search">Navigate the atlas</label>
          <div className="search-box">
            <span aria-hidden="true">/</span>
            <input
              id="atlas-search"
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              placeholder="Paper, concept, author, method..."
              autoComplete="off"
            />
            {search && (
              <button type="button" onClick={() => setSearch("")}>
                Clear
              </button>
            )}
          </div>
          {searchResults.length > 0 && (
            <div className="search-results">
              {searchResults.map((paper) => (
                <button
                  key={paper.id}
                  type="button"
                  onClick={() => selectSearchResult(paper)}
                >
                  <span
                    className="result-orbit"
                    style={{ background: colorForDomain(normalizedDomain(paper)) }}
                  />
                  <span>
                    <strong>{paper.title || "Untitled paper"}</strong>
                    <small>
                      {normalizedDomain(paper)} /{" "}
                      {primaryConcept(paper) || "No narrower concept"}
                    </small>
                  </span>
                </button>
              ))}
            </div>
          )}
        </section>
        <div className="masthead-actions">
          <div className="graph-count">
            {payload ? (
              <>
                <strong>{payload.papers.length}</strong> papers
                <span />
                <strong>{payload.edges.length}</strong> connections
              </>
            ) : (
              "Charting the archive"
            )}
          </div>
          <button
            className="add-paper-button"
            type="button"
            onClick={() => {
              setShowIngest(true);
              setIngestState({ status: "idle" });
            }}
          >
            <span>+</span> Add paper
          </button>
          <a className="about-button" href="/about">
            About
          </a>
        </div>
      </header>

      {uploadNotice && (
        <aside
          className={`upload-notice ${uploadNotice.kind}`}
          role={uploadNotice.kind === "error" ? "alert" : "status"}
          aria-live="polite"
        >
          <span className="notice-mark" aria-hidden="true" />
          <div>
            <strong>{uploadNotice.title}</strong>
            <p>{uploadNotice.message}</p>
          </div>
          <button
            type="button"
            onClick={() => setUploadNotice(null)}
            aria-label="Dismiss upload notice"
          >
            x
          </button>
        </aside>
      )}

      <aside className="atlas-key" aria-label="Knowledge domains">
        <p className="eyebrow">Observed fields</p>
        <div className="domain-list">
          {domains.map((domain) => (
            <button key={domain} type="button" onClick={() => focusDomain(domain)}>
              <span
                className="domain-ring"
                style={{ borderColor: colorForDomain(domain) }}
                aria-hidden="true"
              />
              {domain}
            </button>
          ))}
        </div>
        <div className="symbol-key" aria-label="Map symbol key">
          <p className="eyebrow">Map key</p>
          <div>
            <span className="key-symbol field-symbol" aria-hidden="true" />
            Field
          </div>
          <div>
            <span className="key-symbol topic-symbol" aria-hidden="true" />
            Topic
          </div>
          <div>
            <span className="key-symbol paper-symbol" aria-hidden="true" />
            Paper
          </div>
        </div>
        <p className="key-note">
          Fields and concepts are derived from the papers, not imposed in advance.
        </p>
      </aside>

      <section className="graph-stage" aria-label="STOA knowledge graph">
        {loadState.status === "loading" && (
          <div className="center-state">
            <div className="orbital-loader" />
            <p>Mapping the archive</p>
          </div>
        )}
        {loadState.status === "error" && (
          <div className="center-state error-state">
            <p className="eyebrow">Signal interrupted</p>
            <h2>The atlas could not reach STOA.</h2>
            <p>{loadState.message}</p>
            <p>Start the API with `python -m backend.api`, then refresh.</p>
          </div>
        )}
        {payload && payload.papers.length === 0 && (
          <div className="center-state">
            <p className="eyebrow">An empty sky</p>
            <h2>Ingest a paper to place the first point of light.</h2>
          </div>
        )}
        {payload && payload.papers.length > 0 && (
          <GraphCanvas
            payload={payload}
            selectedId={selectedPaper?.id || null}
            focusId={focusId}
            onSelectPaper={(paper) => {
              setSelectedPaper(paper);
              setRegionNote(null);
            }}
            onSelectRegion={(label, kind) => setRegionNote({ label, kind })}
            onFocusComplete={() => setFocusId(null)}
          />
        )}
        <div className="navigation-hint">
          <span>Scroll to travel</span>
          <span>Drag to chart a course</span>
          <span>Select a light to inspect</span>
        </div>
        {regionNote && !selectedPaper && (
          <div className="region-note">
            <p className="eyebrow">Current region</p>
            <strong>{regionNote.label}</strong>
            <span>Move closer to reveal its papers and concepts.</span>
            <a
              href={`https://www.google.com/search?q=${encodeURIComponent(regionNote.label)}`}
              target="_blank"
              rel="noreferrer"
            >
              Search Google <span aria-hidden="true">+</span>
            </a>
          </div>
        )}
      </section>

      <aside className={`paper-panel ${selectedPaper ? "is-open" : ""}`}>
        {selectedPaper ? (
          <>
            <button
              className="panel-close"
              type="button"
              onClick={() => setSelectedPaper(null)}
              aria-label="Close paper details"
            >
              x
            </button>
            <p className="eyebrow">{normalizedDomain(selectedPaper)}</p>
            <h2>{selectedPaper.title || "Untitled paper"}</h2>
            <p className="paper-byline">
              {selectedPaper.authors.length
                ? selectedPaper.authors.join(", ")
                : "Unknown authors"}
            </p>
            <p className="paper-date">{formatDate(selectedPaper.published)}</p>
            <div className="panel-rule" />
            <p className="paper-summary">
              {selectedPaper.summary || "No summary is available for this paper."}
            </p>
            <div className="metadata-group">
              <span>Concepts</span>
              <div className="tag-list">
                {selectedPaper.concepts.map((concept) => (
                  <span key={concept}>{concept}</span>
                ))}
              </div>
            </div>
            <div className="metadata-group">
              <span>Methods</span>
              <div className="tag-list method-tags">
                {selectedPaper.methods.map((method) => (
                  <span key={method}>{method}</span>
                ))}
              </div>
            </div>
            <a
              className="source-link"
              href={sourceHref}
              target="_blank"
              rel="noreferrer"
            >
              {hasWebSource ? "Read the source" : "Find paper online"} <span>+</span>
            </a>
            {!hasWebSource && (
              <p className="local-source">
                Browsers cannot open the original local file path from this page.
                This searches Scholar using the paper title and author instead.
              </p>
            )}
          </>
        ) : (
          <div className="panel-empty">
            <span className="empty-orbit" />
            <p className="eyebrow">Paper details</p>
            <h2>Select a paper to enter its orbit.</h2>
            <p>
              Nearby lights are papers connected by semantic similarity. Hover to
              reveal a neighborhood.
            </p>
          </div>
        )}
      </aside>

      {showIngest && (
        <div
          className="ingest-backdrop"
          role="presentation"
          onMouseDown={(event) => {
            if (
              event.target === event.currentTarget &&
              ingestState.status !== "working"
            ) {
              setShowIngest(false);
            }
          }}
        >
          <section className="ingest-dialog" role="dialog" aria-modal="true">
            <button
              className="dialog-close"
              type="button"
              onClick={() => setShowIngest(false)}
              disabled={ingestState.status === "working"}
              aria-label="Close add paper dialog"
            >
              x
            </button>
            <p className="eyebrow">Extend the atlas</p>
            <h2>Add a paper</h2>
            <p className="dialog-intro">
              STOA will screen the paper, extract its knowledge, and place it among
              related work.
            </p>
            <div className="ingest-tabs" role="tablist">
              <button
                type="button"
                className={ingestMode === "pdf" ? "active" : ""}
                onClick={() => setIngestMode("pdf")}
                disabled={ingestState.status === "working"}
              >
                Local PDF
              </button>
              <button
                type="button"
                className={ingestMode === "arxiv" ? "active" : ""}
                onClick={() => setIngestMode("arxiv")}
                disabled={ingestState.status === "working"}
              >
                arXiv ID
              </button>
            </div>
            {ingestState.status === "working" ? (
              <div className="ingest-processing" role="status" aria-live="polite">
                <span className="processing-wheel" aria-hidden="true">
                  <span />
                  <span />
                  <span />
                </span>
                <strong>Processing the paper</strong>
                <small>{ingestState.message}</small>
                <div className="processing-track" aria-hidden="true">
                  <span />
                </div>
              </div>
            ) : ingestMode === "pdf" ? (
              <label className="pdf-drop">
                <input
                  ref={fileInputRef}
                  type="file"
                  accept="application/pdf,.pdf"
                  onChange={(event) => ingestPdf(event.target.files?.[0])}
                />
                <span className="upload-orbit" />
                <strong>Choose a PDF from this computer</strong>
                <small>The file is sent directly to your local STOA API.</small>
              </label>
            ) : (
              <form
                className="arxiv-form"
                onSubmit={(event) => {
                  event.preventDefault();
                  ingestArxiv();
                }}
              >
                <label htmlFor="arxiv-id">arXiv identifier</label>
                <input
                  id="arxiv-id"
                  value={arxivId}
                  onChange={(event) => setArxivId(event.target.value)}
                  placeholder="2301.04567"
                />
                <button
                  type="submit"
                  disabled={!arxivId.trim()}
                >
                  Pull from arXiv
                </button>
              </form>
            )}
            {ingestState.status === "error" && (
              <div className={`ingest-status ${ingestState.status}`}>
                <p>{ingestState.message}</p>
              </div>
            )}
          </section>
        </div>
      )}
    </main>
  );
}
