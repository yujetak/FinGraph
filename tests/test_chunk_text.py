from src.graphBuilder.neo4j.finGraph import chunk_text


def test_chunk_text_empty_returns_empty_list():
    assert chunk_text("") == []

def test_chunk_text_none_returns_empty_list():
    assert chunk_text(None) == []

def test_chunk_text_short_text_returns_single_chunk():
    result = chunk_text("짧은 텍스트", size=500, overlap=50)
    assert len(result) == 1

def test_chunk_text_long_text_splits_into_multiple_chunks():
    result = chunk_text("가" * 1000, size=500, overlap=50)
    assert len(result) >= 2
