"""Check repository-local Markdown and HTML links without network requests."""
from html.parser import HTMLParser
from pathlib import Path
import re
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1]


class References(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []

    def handle_starttag(self, tag, attrs):
        for key, value in attrs:
            if key in {"src", "href", "srcset"} and value:
                self.links.append(value)


def main():
    errors = []
    count = 0
    for path in ROOT.rglob("*.md"):
        relative = path.relative_to(ROOT)
        if any(part in {".git", ".venv", "node_modules", "kb", "outputs"} for part in relative.parts):
            continue
        content = path.read_text(encoding="utf-8-sig")
        content = re.sub(r"```.*?```", "", content, flags=re.S)
        parser = References()
        parser.feed(content)
        for link in re.findall(r"\]\(([^)]+)\)", content) + parser.links:
            url = urlsplit(link)
            if url.scheme or not url.path:
                continue
            target = path.parent / unquote(url.path)
            count += 1
            if not target.exists():
                errors.append(f"{relative}: {link}")
    if errors:
        raise SystemExit("Broken document links:\n" + "\n".join(errors))
    print(f"PASS: {count} repository-local document links")


if __name__ == "__main__":
    main()
