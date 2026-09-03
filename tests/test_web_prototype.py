import json
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlsplit

WEB = Path(__file__).resolve().parents[1] / "prototypes/web-review/web"


class Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.paths = []

    def handle_starttag(self, tag, attrs):
        for key, value in attrs:
            if key in {"src", "href"} and value:
                url = urlsplit(value)
                if not url.scheme and url.path:
                    self.paths.append(url.path)


def test_prototype_local_assets_exist():
    parser = Links()
    parser.feed((WEB / "index.html").read_text())
    assert parser.paths
    for path in parser.paths:
        assert (WEB / path).is_file(), path
    assert (WEB / "vendor/pdf.worker.min.js").is_file()


def test_prototype_dataset_contains_all_three_document_types():
    data = json.loads((WEB / "data/dataset.json").read_text())
    assert {sample["doc_type"] for sample in data["samples"]} == {
        "flow",
        "source",
        "aggregate_mart",
    }
    for sample in data["samples"]:
        assert sample["text"] and sample["blocks"]
    assert set(data["blank_templates"]) == {"flow", "source", "aggregate_mart"}


def test_learning_is_explicitly_demo():
    data = json.loads((WEB / "data/learning.json").read_text())
    assert data["demo"] is True
    assert "UX-прототип, не production-анализ" in (WEB / "index.html").read_text()
