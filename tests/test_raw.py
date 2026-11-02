from src import loaders


def test_raw_unchanged():
    assert loaders.verify_raw() == []
