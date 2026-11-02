#!/usr/bin/env python3
"""Keep the plain GitHub-rendered year in the profile README current."""
from datetime import datetime, timezone
from pathlib import Path
import re

readme = Path("README.md")
text = readme.read_text(encoding="utf-8")
start = "<!-- PROFILE_YEAR_START -->"
end = "<!-- PROFILE_YEAR_END -->"
pattern = re.compile(re.escape(start) + r"[\s\S]*?" + re.escape(end))
year = datetime.now(timezone.utc).year
replacement = f'{start}\n<p align="center"><sub>{year}</sub></p>\n{end}'

if len(pattern.findall(text)) != 1:
    raise RuntimeError("Expected exactly one managed profile year block")

updated = pattern.sub(lambda _: replacement, text)
if updated != text:
    readme.write_text(updated, encoding="utf-8")
    print(f"Updated profile year to {year}")
else:
    print(f"Profile year already current: {year}")
