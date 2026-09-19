"""
Unit tests for the TF-IDF matchmaking core, isolated from Redis/DB.
"""
from app.matchmaking import _vectorize
from sklearn.metrics.pairwise import cosine_similarity


def test_similar_interests_score_higher_than_dissimilar():
    corpus = [
        "hiking camping mountains nature",   # query
        "hiking camping outdoors trails",    # similar
        "cooking recipes baking desserts",   # dissimilar
    ]
    vectors = _vectorize(corpus)
    sims = cosine_similarity(vectors[0:1], vectors[1:])[0]

    assert sims[0] > sims[1], "Similar interest text should score higher than unrelated text"


def test_empty_corpus_does_not_crash():
    vectors = _vectorize(["", "", ""])
    assert vectors.shape[0] == 3
