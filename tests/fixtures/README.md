# Test fixtures — NOT real search results

These JSON files are **synthetic test fixtures** shaped like SerpApi responses
(Google Scholar API and Extract API). Every title starts with `[TEST FIXTURE]`
and every link points to `example.org`. They exist only so the evidence
pipeline can be unit-tested offline. The application never serves them, and
they must never be copied into `data/cache/`.
