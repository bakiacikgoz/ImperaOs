from pathlib import Path


def test_canonical_and_compatibility_packages_are_present() -> None:
    assert Path("imperaos/__main__.py").exists()
    assert Path("binliquid/__main__.py").exists()
    pyproject = Path("pyproject.toml").read_text(encoding="utf-8")
    assert 'imperaos = "imperaos.cli:app"' in pyproject
    assert 'binliquid = "binliquid.__main__:main"' in pyproject
