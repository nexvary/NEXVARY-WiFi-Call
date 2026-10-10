#!/usr/bin/env python3
"""Validate the seven supported Android locales without needing an Android SDK.

Catch missing translations, duplicate resource names, incompatible formatting,
and AAPT-sensitive punctuation before the more expensive Android build.
"""
from pathlib import Path
import re
import sys
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
RESOURCE_ROOT = ROOT / "app/src/main/res"
LOCALES = ("values", "values-ar", "values-tr", "values-es", "values-de", "values-it", "values-fr")
# Java/Android Formatter arguments; %% and %n do not consume an argument.
FORMAT = re.compile(r"%(?:(\d+)\$)?[-#+ 0,(<]*\d*(?:\.\d+)?([a-zA-Z%])")
errors = []


def placeholders(value):
    result = []
    next_index = 1
    for match in FORMAT.finditer(value):
        index, conversion = match.groups()
        if conversion in ("%", "n"):
            continue
        if index is None:
            index = str(next_index)
            next_index += 1
        result.append((int(index), conversion))
    return sorted(result)


def read_strings(folder):
    path = RESOURCE_ROOT / folder / "strings.xml"
    try:
        resource = ET.parse(path).getroot()
    except (OSError, ET.ParseError) as exc:
        errors.append(f"{folder}: {exc}")
        return {}
    strings = {}
    for element in resource.findall("string"):
        name = element.get("name", "")
        text = "".join(element.itertext())
        if name in strings:
            errors.append(f"{folder}: duplicate string {name}")
        if not text.strip():
            errors.append(f"{folder}/{name}: empty translation")
        # Android accepts apostrophes within a double-quoted string. Otherwise
        # they must be escaped after XML decoding, including &apos; entities.
        quoted = text.startswith('"') and text.endswith('"')
        if not quoted and re.search(r"(?<!\\)(?:\\\\)*'", text):
            errors.append(f"{folder}/{name}: apostrophe requires Android escaping")
        if re.search(r"(?<!\\)@|(?<!\\)\?", text[:1]):
            errors.append(f"{folder}/{name}: leading @ or ? requires escaping")
        strings[name] = text
    return strings


resources = {folder: read_strings(folder) for folder in LOCALES}
default = resources["values"]
for folder, strings in resources.items():
    for name in sorted(default.keys() - strings.keys()):
        errors.append(f"{folder}: missing translation {name}")
    for name in sorted(strings.keys() - default.keys()):
        errors.append(f"{folder}: no default resource for {name}")
    for name in default.keys() & strings.keys():
        if placeholders(default[name]) != placeholders(strings[name]):
            errors.append(f"{folder}/{name}: format arguments differ from default")

# Ensure the Compose UI cannot refer to a resource that exists in no locale.
for source in (ROOT / "app/src/main/java").rglob("*.kt"):
    for name in re.findall(r"\bR\.string\.(\w+)", source.read_text()):
        if name not in default:
            errors.append(f"{source.relative_to(ROOT)}: missing default string {name}")

if errors:
    print("Android string resource validation failed:", file=sys.stderr)
    print("\n".join(f"- {error}" for error in errors), file=sys.stderr)
    sys.exit(1)
print(f"Validated {len(LOCALES)} locales with {len(default)} strings each; references and format arguments match.")
