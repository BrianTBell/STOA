type AboutPageProps = {
  onReturn: () => void;
};

const pipelineSteps = [
  ["01", "Read", "Local PDF or arXiv text enters the pipeline."],
  ["02", "Screen", "Obvious junk and unreadable papers stop early."],
  ["03", "Extract", "Claude identifies the summary, concepts, methods, and field."],
  ["04", "Resolve", "Terms reconcile against STOA's evolving vocabulary."],
  ["05", "Embed", "A local model converts the paper's meaning into a vector."],
  ["06", "Place", "The paper joins its three nearest eligible neighbors."],
];

export default function AboutPage({ onReturn }: AboutPageProps) {
  return (
    <article className="about-page">
      <section className="about-hero">
        <div className="about-hero-copy">
          <p className="eyebrow">How the atlas works</p>
          <h2>A map of knowledge that emerges from research papers themselves.</h2>
          <p>
            STOA organizes academic work by semantic proximity rather than
            citations, journal categories, or a taxonomy imposed in advance.
            Every new paper can subtly redraw the map.
          </p>
          <button type="button" onClick={onReturn}>
            Return to the atlas <span aria-hidden="true">+</span>
          </button>
        </div>
        <div className="about-hero-orbit" aria-hidden="true">
          <span className="hero-field-ring" />
          <span className="hero-topic-diamond topic-one" />
          <span className="hero-topic-diamond topic-two" />
          <span className="hero-paper paper-one" />
          <span className="hero-paper paper-two" />
          <span className="hero-paper paper-three" />
          <i className="orbit-line orbit-one" />
          <i className="orbit-line orbit-two" />
          <i className="orbit-line orbit-three" />
        </div>
      </section>

      <section className="about-section">
        <div className="section-heading">
          <p className="eyebrow">From source to star</p>
          <h3>How a paper enters STOA</h3>
          <p>
            One shared pipeline serves both the command line and the website.
            The original document text is used for processing, then discarded.
          </p>
        </div>
        <div className="pipeline-diagram">
          {pipelineSteps.map(([number, title, description], index) => (
            <div className="pipeline-step" key={number}>
              <span className="pipeline-number">{number}</span>
              <div className="pipeline-node">
                <span>{index === pipelineSteps.length - 1 ? "◆" : "●"}</span>
              </div>
              <strong>{title}</strong>
              <p>{description}</p>
            </div>
          ))}
        </div>
      </section>

      <section className="about-section connection-section">
        <div className="section-heading">
          <p className="eyebrow">Connection logic</p>
          <h3>Every paper chooses its own nearest three.</h3>
          <p>
            Cosine similarity is calculated from a local semantic embedding.
            Eligible neighbors must score at least 0.65. As stronger papers
            arrive, weaker nominations can be displaced.
          </p>
        </div>
        <div className="connection-layout">
          <div className="nomination-diagram" aria-label="Similarity connection diagram">
            <span className="diagram-paper selected-paper">Selected paper</span>
            <span className="diagram-paper match-one">Match 1</span>
            <span className="diagram-paper match-two">Match 2</span>
            <span className="diagram-paper match-three">Match 3</span>
            <span className="diagram-paper incoming-paper">Incoming</span>
            <i className="diagram-edge gold-edge edge-one" />
            <i className="diagram-edge gold-edge edge-two" />
            <i className="diagram-edge gold-edge edge-three" />
            <i className="diagram-edge gray-edge edge-four" />
          </div>
          <div className="connection-legend">
            <div>
              <span className="legend-line gold" />
              <p>
                <strong>Gold</strong>
                The selected paper chose this neighbor.
              </p>
            </div>
            <div>
              <span className="legend-line gray" />
              <p>
                <strong>Gray</strong>
                This neighbor chose the selected paper.
              </p>
            </div>
            <small>
              A paper may display more than three total connections because
              other papers can independently choose it.
            </small>
          </div>
        </div>
      </section>

      <section className="about-section">
        <div className="section-heading">
          <p className="eyebrow">Reading the atlas</p>
          <h3>Move through knowledge by scale.</h3>
        </div>
        <div className="zoom-cards">
          <div className="zoom-card">
            <span className="zoom-level">Far</span>
            <span className="about-symbol field-symbol" />
            <h4>Fields</h4>
            <p>Broad regions remain visible when surveying the whole atlas.</p>
          </div>
          <div className="zoom-card">
            <span className="zoom-level">Closer</span>
            <span className="about-symbol topic-symbol" />
            <h4>Topics</h4>
            <p>Concept landmarks appear as you approach a field.</p>
          </div>
          <div className="zoom-card">
            <span className="zoom-level">Near</span>
            <span className="about-symbol paper-symbol" />
            <h4>Papers</h4>
            <p>Individual titles emerge at the most detailed scale.</p>
          </div>
        </div>
        <p className="layout-note">
          Field placement is graph-derived: cross-field paper connections pull
          related regions nearer, while collision spacing keeps every region
          legible. Distance is a relative navigation signal, not an exact metric.
        </p>
      </section>

      <section className="about-section change-section">
        <div className="section-heading">
          <p className="eyebrow">A living graph</p>
          <h3>The map changes when knowledge grows.</h3>
          <p>
            A new paper is compared with every existing embedding. It chooses
            its nearest neighbors, then STOA updates only the existing papers
            whose top-three lists changed.
          </p>
        </div>
        <div className="change-diagram">
          <div className="change-state">
            <span>Before</span>
            <div>
              <i className="mini-paper central" />
              <i className="mini-paper satellite a" />
              <i className="mini-paper satellite b" />
              <i className="mini-paper satellite c" />
              <i className="mini-edge a" />
              <i className="mini-edge b" />
              <i className="mini-edge c" />
            </div>
          </div>
          <span className="change-arrow">→</span>
          <div className="change-state after">
            <span>New paper arrives</span>
            <div>
              <i className="mini-paper central" />
              <i className="mini-paper satellite a" />
              <i className="mini-paper satellite b" />
              <i className="mini-paper satellite new" />
              <i className="mini-edge a" />
              <i className="mini-edge b" />
              <i className="mini-edge new" />
            </div>
          </div>
        </div>
      </section>

      <section className="about-section boundaries-section">
        <div>
          <p className="eyebrow">AI structures</p>
          <h3>What the system does</h3>
          <ul>
            <li>Screens malformed or non-paper input</li>
            <li>Extracts summaries, concepts, methods, and fields</li>
            <li>Reconciles terms against a shared vocabulary</li>
            <li>Calculates semantic proximity with a local embedding model</li>
          </ul>
        </div>
        <div>
          <p className="eyebrow">Humans value</p>
          <h3>What the system does not do</h3>
          <ul>
            <li>Judge whether a paper is true, important, or good science</li>
            <li>Create similarity edges from Claude's subjective opinion</li>
            <li>Store the full source document after processing</li>
            <li>Treat the current map as a permanent taxonomy</li>
          </ul>
        </div>
      </section>

      <footer className="about-footer">
        <p>STOA is currently a single-user, paper-first prototype.</p>
        <button type="button" onClick={onReturn}>
          Explore the living atlas
        </button>
      </footer>
    </article>
  );
}
