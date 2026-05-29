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
Working it now...