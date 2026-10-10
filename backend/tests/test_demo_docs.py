import hashlib

from scripts.generate_demo_docs import generate


def test_generates_all_documents_deterministically(tmp_path):
    first = generate(tmp_path / "a")
    second = generate(tmp_path / "b")
    names = sorted(p.name for p in first)
    assert len([n for n in names if n.startswith(("sunrise", "lakeview", "anand", "citydx", "medline"))]) == 9
    assert len([n for n in names if n.startswith("greenfield")]) == 3

    def digest(p):
        return hashlib.sha256(p.read_bytes()).hexdigest()

    # Stable hashes keep DEMO_CACHE valid across regenerations.
    assert [digest(p) for p in first] == [digest(p) for p in second]
