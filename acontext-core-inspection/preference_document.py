"""Read and patch known preference sections without rewriting unrelated evidence."""
import re
import yaml

FIELDS = {
    "rule": ("Prefer", "偏好"),
    "scope": ("Applies When", "适用范围", "适用条件"),
    "exceptions": ("Exceptions", "例外"),
}


def sections(content):
    lines = content.splitlines(keepends=True)
    result = []
    fence = None
    for index, line in enumerate(lines):
        marker = re.match(r"^\s*(`{3,}|~{3,})", line)
        if marker:
            char = marker[1][0]
            fence = None if fence == char else char if fence is None else fence
        if fence is None:
            heading = re.match(r"^##[ \t]+(.+?)[ \t]*\r?\n?$", line)
            if heading:
                result.append((heading[1], index))
    return lines, [(name, start, result[i + 1][1] if i + 1 < len(result) else len(lines))
                   for i, (name, start) in enumerate(result)]


def preference_fields(content):
    lines, spans = sections(content)
    return {field: "\n\n".join(re.sub(r"\n?<!-- preference-control: .*? -->", "", "".join(lines[start + 1:end])).strip()
                              for name, start, end in spans if name in names)
            for field, names in FIELDS.items()}


def patch_preference(content, changes):
    fields = preference_fields(content)
    changed = []
    for field, names in FIELDS.items():
        value = changes.get(field)
        if value is None or value.strip() == fields[field]:
            continue
        lines, spans = sections(content)
        matches = [(start, end) for name, start, end in spans if name in names]
        if len(matches) > 1:
            raise ValueError("Repeated preference sections; consolidate this record before editing")
        text = value.strip()
        if matches:
            start, end = matches[0]
            content = "".join(lines[:start + 1]) + text + "\n\n" + "".join(lines[end:])
        elif text:
            content = content.rstrip() + f"\n\n## {names[0]}\n{text}\n"
        changed.append(field)
    summary = changes.get("summary")
    if summary is not None:
        front = re.match(r"\A---\s*\n([\s\S]*?)\n---[ \t]*\r?\n", content)
        if not front:
            raise ValueError("Preference front matter unavailable")
        data = yaml.safe_load(front[1])
        if not isinstance(data, dict):
            raise ValueError("Invalid preference front matter")
        if summary.strip() != data.get("description"):
            data["description"] = summary.strip()
            content = "---\n" + yaml.safe_dump(data, allow_unicode=True, sort_keys=False) + "---\n" + content[front.end():]
            changed.append("summary")
    return content, changed
