This file is a notebook I use through development. More or less its my informal take how developing each phase went.


-------------------- Phase 1 --------------------
I have a pretty good system for breaking papers into information for graphDB embeddings, and info to display on the site.
There are two pipelines where graph attributes are extracted emergently. 

Initially I started with only an ArXiv pipeline.About a week ago when I started this is seemed like a great place to source 
free papers across several technical domains, especially considering their API. This ArXiv pipeline queries both the paper 
as a PDF, and its listed metadata on ArXiv. This is collated into a JSON file and send to claude, along with a ArXiv tailored
prompt, to extract the appropriate attributes.

I started using sonnet 4.6 but it was more costly than I'd like, something like 5 cents a query. I actually
did a pretty solid job optimizing my prompt and switching to haiku 4.5 to achieve comparable results at about 1/4, 1/5
the token cost.

This ArXiv pipeline was working well last weekend when I started developing, but tonight I started hitting 429 Errors on my 
first metadata query. Kind of weird cause I'm not hammering the API, in fact I'm completely abiding by their API docs.
This lead me to develop another pipeline for local PDF upload. I think in the long term this is actually the direction to lean.
The fact that ArXiv uses the metadata as well as the PDF is not super realist in regard to how someone would want to use the tool.
Anyway, this pipeline takes a local PDF path, parses it to text and send its to claude. Claude returns a JSON file with the papers 
fingerprint to be used in both the graphDB and the website.

I took a 5-paper sample for testing, basically just assessing claude attribute take against the contents of the paper. I had codex
work as backup and do its own audit too. Haiku 4.5 did surprisingly well. I believe derived attributes are on point enough
to provide a reasonable useful graphDB. Honestly, I've never implemented a graphDB for something like this, so we'll see
how it actually pans out later. I went through 6 or so prompt iterations and hit diminishing returns fast. I wouldn't be surprised
if I'm hitting hitting model limits. Unfortunately I'm working a tight margin with $$$, accuracy, and fun with this project.

All considered I think, and hope this PDF parsing pipeline will be able to hold me over for the rest of prototype development.



-------------------- Phase 2 --------------------
I came back today for Phase 2, quick note to self on Phase 2 CLI commands...

python -m backend.ingest <arxiv_id> --store
python -m backend.ingest --pdf <path> --store
python -m backend.store list
python -m backend.store get <paper_id>

Anyway, Phase 1 handled article ingestion, Phase 2 is gets at storing the info. Went with a free Neo4j account with this that will
give some 200k nodes and 400k relationships. I think thats good for a prototype? We'll see. Parsed info from phase 1 ingestion 
pipeline will get gets cleaned, converted to a dict, then shot to neo4j to be merged into the DB as a new paper. It does check
for unique ID constraints, which at this point is either an ArXiv ID, or PDF hash string. the extracted fields from the DB
get written as the paper nodes properties then neo4j returns the stored node.

That is the basic pipeline, I also added ways to query a single paper, list all, and delete papers as shown above, kind of. Here's
an example of a training paper's fingerprint queried from the DB.

[
  {
    "summary": "This paper provides a comprehensive introduction to reinforcement learning (RL), covering fundamental concepts such as states, actions, policies, rewards, and transition dynamics. It presents an overview of RL algorithms categorized by key factors including model-free, model-based, value-based, and policy-based approaches, along with resources for learning and implementation.",
    "concepts": [
      "reinforcement learning",
      "markov decision process",
      "policy",
      "reward function",
      "value function",
      "model-free methods",
      "model-based methods",
      "multi-armed bandit"
    ],
    "updated_at": "2026-05-29T18:10:36.782670+00:00",
    "methods": [
      "policy gradient methods",
      "proximal policy optimization",
      "value-based learning",
      "policy-based learning"
    ],
    "domain": "reinforcement learning",
    "created_at": "2026-05-29T18:10:36.782670+00:00",
    "id": "localpdf:bd708036be63e6a1",
    "title": "Introduction to Reinforcement Learning",
    "source_url": "somewhere on my pc :)",
    "authors": [
      "Majid Ghasemi",
      "Dariush Ebrahimi"
    ]
  }
]



-------------------- Phase 3 --------------------
This phase handles embedding. The idea a papers fingerprint as shown above and convert it into an embedding which we can create
a vector index with. The two big things here are the python framework sentence-transformers, and again Neo4j 

A tangent, the concept of embeddings recently clicked for me. This is two years after first heard about it. 
Back then an into ML lecturer gave me an example where a CNN breaks images down into... data (he didnt really explain)... then it 
can use this info to distinguish between different things. The example he gave was a graph with a straight line, with a dog on one 
side, and a cat on the other. "Classification" he said. incredible. I've recently been reading Rashka's, Build an LLM from Scratch, 
which explains this much, much better. Beyond that, this project phase has been an awesome way to really apply it. 

The attributes of a paper ingested will now be parsed by an all-MiniLM-L6-v2 embedding model into a 384-number embedding. Neo4j 
is told to use the a queryable vector. Queried similarity between a few papers and got pretty promising results...
"Introduction to Reinforcement Learning" matches "Reinforcement Learning: A Survey" at 0.9003 and "A Tutorial Introduction to 
Reinforcement Learning" at 0.8883 which is pretty cool.

This has kind of been shoved into the previous pipeline, so at a high level its now working like is now like:
upload source paper → extract text → claude extracts fields → sentence-transformers creates embedding → kick to Neo4j, store, & create vector index.



-------------------- Phase 4 --------------------
Phase 4, I'm trying to weed out noise. I'm concerned claude will return a variety of attributes across different papers that are basically
aliases for the same thing. Why does that matter? Super extreme case, but I think it would be cool if this could grow to capture a ton of data,
so much that's its basically a web of all human knowledge... sounds familiar. Imagine you grew this data without auditing for similar terms,
then when you went to filter the graph web by terms you see, RL, Reinforcement Learning, Deep RL, Deep Reinforcement Learning. I'm trying 
to avoid that mess. 

My phase 4 logic is as follows... ingest paper & get fingerprint → audit attributes against vocab containing emergent aliases → note resuloved
and unresolved terms (matches and new words respectively)→ for each unresolved term note attribute type (domain,
method, concept), use this to narrow down relevant vocab to send to claude → send claude the blacklist and the narrowed vocab to compare for new alias,
or new word → get back claude results → add new vocab node or alias attribute appropriately (neo4j) → alter fingerprint attributes per claude audit →
send to neo4j as new paper node. 

Having come to a point of completion with the phase I can say it was trickier than others. The majority of the work was optimizing the claude prompt.
At first claude was quick to mark unresolved words into aliases. Seems like when it was unsure it would lean towards merging into a known words.
Telling it to add a new word when it was unsure helped a lot. I am working with claude's haiku 4.5 and RL research papers. Maybe the model isn't PHD trained
in this technical domain. I imagine recognizing like technical terms is harder for haiku 4.5 than first extracting the words mentioned in the paper.
This is at a point where there are still some weird alias merges, like live control → visual control, but overall this is good. My gut tells me
not to add to the prompt for the sake of noise, and I might be hitting model limits. I'd be inclined to try on a stronger model later. I recognize
the data will be a little poisoned moving forward with the current implementation, but I'm willing to work it later. Worst case I have the pleasure
of doing large DB cleanup later, which could be another good learning opportunity.



-------------------- Phase 5 --------------------
I think I have hit my first real road block. The plan was to have claude generate descriptive edges that would help the user navigate more intuitively
through the graph. It would show semantics like BUILDS_ON, PRECURSOR_OF, CONTRADICTS, SIMILAR_TO on edges. Now that I'm implementing I foresee a real issue
that slipped past me initially. Claude would have to analyze n nearest neighbors in full, and some of the papers are 50+ pages. That will heavy lifting 
for my budget. The other option is to compare article footprints stored in Neo4j. The issue there is an abstract, title, and metadata labels definitely 
aren't enough the elucidate if one paper builds on another, or was a precursor, etc. 

I think a fair compromise is to rely on embedding proximity alone. This isn't as nice for users, but I'd rather say less and let the people figure it out,
over potentially guiding them incorrectly. This can be done manually with python alone too, so that nice. 

I'm using a somewhat arbitrary embedding proximity threshold of 0.8, which I plan on tuning later in testing. Each new papers has "similar to" connections
added between it and its 3 nearest neighbors. I'm thinking this is a good, sparse number of edges for users to see, especially because technical papers
can be so dense. Could be a cool quirk down the line to have some sort of reading or completion tracker like kahn academy of duolingo, but obviously way
cooler, somehow.


                             .-----.
                            /7  .  (
                           /   .-.  \
                          /   /   \  \
                         / `  )   (   )                *I've spent a total of 48 cents so far
                        / `   )   ).  \
                      .'  _.   \_/  . |             
     .--.           .' _.' )`.        |
    (    `---...._.'   `---.'_)    ..  \                        Forty-eight pennies—
     \            `----....___    `. \  |                           
      `.           _ ----- _   `._  )/  |                 the model thinks, therefore it is
        `.       /"  \   /"  \`.  `._   |                       
          `.    ((O)` ) ((O)` ) `.   `._\                       slightly less wealthy
            `-- '`---'   `---' )  `.    `-.
               /                  ` \      `-.
             .'                      `.       `.
            /                     `  ` `.       `-.
     .--.   \ ===._____.======. `    `   `. .___.--`     .''''.
    ' .` `-. `.                )`. `   ` ` \          .' . '  8)
   (8  .  ` `-.`.               ( .  ` `  .`\      .'  '    ' /
    \  `. `    `-.               ) ` .   ` ` \  .'   ' .  '  /
     \ ` `.  ` . \`.    .--.     |  ` ) `   .``/   '  // .  /
      `.  ``. .   \ \   .-- `.  (  ` /_   ` . / ' .  '/   .'
        `. ` \  `  \ \  '-.   `-'  .'  `-.  `   .  .'/  .'
          \ `.`.  ` \ \    ) /`._.`       `.  ` .  .'  /
    LGB    |  `.`. . \ \  (.'               `.   .'  .'
        __/  .. \ \ ` ) \                     \.' .. \__
 .-._.-'     '"  ) .-'   `.                   (  '"     `-._.--.
(_________.-====' / .' /\_)`--..__________..-- `====-. _________)
                 (.'(.'

                        (Thank you lgbeard)



-------------------- Phase 6 --------------------
Today I pushed from a somewhat complete phase one trough a complete phase 6. I am tired, but happy. Digressing, phase 6 was initially about
creating a baseline confidence signal for paper quality. I set this goal up when I was planning the project, before I actually implemented
anything. When I came across this it kind of made me roll my eyes.  I don't think haiku, or claude should be creating a baseline signal.
To some extent, I don't think haiku will be well trained enough to derive an accurate quality signal. In another sense I don't think AI 
should be rating someones work. Probably best for the community to do it. And even with that, there's not perfect voting method. I'd need to 
figure out a way where some small group cant gate keep either. Maybe anonymous community voting as a baseline, I'd have to read into it.   

Back to this project... I redirected phase six toward implementing a simple preliminary screening phase in the pipeline. The idea is to 
stop people from uploading garbage. Claude does a quick check for things like basic academic structure, technical contents. I tested this
with two academic papers, one newspaper from the 60's and one from the 80's. screens passed on the academic papers. The 80's was rejected 
due to its contents (win), and the 60's was rejected because it couldn't be scanned. That 60's one was actually a failure mode I hadn't tested.
It failed hard, so I added an softer super duper elegant failure. 

This phase was a lot easier than others, but obviously it was made simpler through the redirection. Regardless, I'm happy with it all.
One step closer to a GUI to play with.



-------------------- Phase 7 --------------------
Coming Soon...