import ast
import re
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass
class Finding:
    rule: str
    severity: str
    line: int
    message: str
    recommendation: str


PATTERNS = [
    ("hardcoded-secret", "high", re.compile(r"(?i)(api[_-]?key|secret|password)\s*=\s*['\"][^'\"]{8,}['\"]"), "A possible secret is hard-coded.", "Load the value from an environment variable or secret store."),
    ("command-injection", "high", re.compile(r"(?i)(os\.system|subprocess\.(?:run|popen|call)|child_process\.exec)\s*\("), "A process is started; untrusted input could cause command injection.", "Use an argument list, an allowlist, no shell, and strict input validation."),
    ("unsafe-eval", "high", re.compile(r"(?i)(?<![\w.])(eval|exec)\s*\("), "Dynamic code evaluation is used.", "Replace dynamic evaluation with a parser or explicit dispatch table."),
    ("sql-concatenation", "high", re.compile(r"(?i)(select|insert|update|delete).{0,80}(\+|\.format\(|f['\"])"), "SQL may be assembled from strings.", "Use parameterized statements or an ORM."),
    ("weak-hash", "medium", re.compile(r"(?i)(md5|sha1)\s*\("), "A weak hash function is used.", "Use Argon2id for passwords or SHA-256/512 where a general digest is required."),
    ("insecure-random", "medium", re.compile(r"(?i)random\.(random|randint|choice)\s*\("), "A non-cryptographic random generator is used.", "Use a cryptographic random source for tokens, passwords, or security decisions."),
    ("xss", "high", re.compile(r"(?i)(innerHTML\s*=|dangerouslySetInnerHTML|document\.write\s*\()"), "Potential unsafe HTML output was found.", "Use textContent or sanitize with a well-maintained allowlist sanitizer."),
    ("path-traversal", "medium", re.compile(r"(?i)(open|readFile|writeFile)\s*\([^\n]*(request|req\.|input|user)"), "A user-controlled value may reach a file path.", "Resolve against a fixed root and reject absolute paths, symlinks, and parent traversal."),
    ("verify-disabled", "high", re.compile(r"(?i)(verify\s*=\s*false|rejectUnauthorized\s*:\s*false)"), "TLS certificate verification is disabled.", "Keep certificate verification enabled and install the correct trust chain."),
]


def review_code(content: str, filename: str = "code.txt") -> dict:
    findings: list[Finding] = []
    suffix = Path(filename).suffix.lower()
    if suffix == ".py":
        try:
            ast.parse(content, filename=filename)
        except SyntaxError as exc:
            findings.append(
                Finding("python-syntax", "high", exc.lineno or 1, exc.msg, "Correct the syntax and run the check again.")
            )
    if suffix in {".json"}:
        import json

        try:
            json.loads(content)
        except json.JSONDecodeError as exc:
            findings.append(Finding("json-syntax", "high", exc.lineno, exc.msg, "Correct the JSON syntax."))

    for rule, severity, pattern, message, recommendation in PATTERNS:
        for match in pattern.finditer(content):
            line = content.count("\n", 0, match.start()) + 1
            findings.append(Finding(rule, severity, line, message, recommendation))
            if len(findings) >= 100:
                break
    order = {"critical": 4, "high": 3, "medium": 2, "low": 1, "information": 0}
    findings.sort(key=lambda item: (-order.get(item.severity, 0), item.line))
    highest = max((order.get(item.severity, 0) for item in findings), default=0)
    label = next((name for name, level in order.items() if level == highest), "information")
    return {
        "filename": filename,
        "risk": label,
        "findings": [asdict(item) for item in findings],
        "checked": len(content),
    }
