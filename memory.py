import numpy as np
from collections import deque
from sklearn.feature_extraction.text import TfidfVectorizer

class AgentMemory:
    def __init__(self, max_size=100, embed_dim=32):
        # Raw text events
        self.events = deque(maxlen=max_size)
        # Simple TF‑IDF vectorizer to embed text → high‑dim sparse
        self.vectorizer = TfidfVectorizer(max_features=embed_dim)
        # Running corpus
        self.corpus = []

    def write(self, event: str):
        # Add event to memory
        self.events.append(event)
        self.corpus.append(event)
        self.vectorizer.fit(self.corpus)

    def read(self, query, top_k=5):
        # Return the average embedding of the top_k most relevant past events
        if not self.events:
            return np.zeros(self.vectorizer.max_features)

        # Embed all events + query
        all_texts = list(self.events) + [query]
        tfidf = self.vectorizer.transform(all_texts).toarray()
        query_vec = tfidf[-1]
        event_vecs = tfidf[:-1]

        # Cosine similarity
        sims = event_vecs @ query_vec / (np.linalg.norm(event_vecs, axis=1)*np.linalg.norm(query_vec)+1e-8)
        top_idxs = np.argsort(sims)[-top_k:]

        # Return the average embeddings
        return event_vecs[top_idxs].mean(axis=0)
    
    def get_memory(self):
        # Return the events as a array of vectors with length 32
        if not self.events:
            return np.zeros(32, dtype=np.float32)
        tfidf = self.vectorizer.transform([' '.join(self.events)]).toarray()[0]

        mem = np.zeros(32, dtype=np.float32)
        mem[:min(32, len(tfidf))] = tfidf[:32]
        return mem
