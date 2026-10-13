# Inverted indexes and ranking

An inverted index maps each term to documents containing it. A posting stores
a document identifier and term frequency. Search visits candidate documents
through postings. BM25 combines term frequency, document length, and inverse
document frequency. A common term usually distinguishes documents poorly.
