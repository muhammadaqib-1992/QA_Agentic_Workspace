#!/usr/bin/env python
"""Term-frequency profile of meeting transcripts, for building a call index.

RUN this script - do not read it into context. Only its output costs tokens.

A transcript is 1-3 hours of speech; reading 36 of them is not affordable. This
prints one line per file - date, length, main speakers, and which domain terms
dominate - which is enough to route a question to the right call. It is NOT a
summary: it says what a call spent time on, never what was decided.

    python profile_transcripts.py knowledge-base/call-recordings

Add project vocabulary to GLOSSARY below as the project's language settles.
"""
import argparse
import collections
import os
import glob
import re

GLOSSARY = [
    "purchase order", "sales order", "work order", "item fulfillment", "item receipt",
    "invoice", "credit memo", "journal entry", "bank reconciliation", "chart of accounts",
    "subsidiary", "intercompany", "budget", "forecast",
    "inventory", "warehouse", "bin", "lot", "serial", "assembly", "landed cost", "costing",
    "pricing", "price level", "discount", "commission", "rebate",
    "vendor", "customer", "contact", "opportunity", "estimate", "quote",
    "saved search", "workflow", "suitelet", "script", "custom record", "custom field",
    "custom segment", "role", "permission", "approval",
    "integration", "rest", "csv", "import", "migration", "cutover",
    "go live", "go-live", "uat", "training", "sandbox", "production",
    "report", "dashboard", "tax", "currency", "exchange rate", "revenue recognition",
    "amortization", "fixed asset", "depreciation", "expense report", "timesheet", "project",
    "shopify", "salesforce", "edi", "celigo", "boomi",
    "payroll", "employee", "receivable", "payable", "payment", "deposit", "statement",
    "collection", "shipping", "freight", "carrier", "3pl", "routing",
    "defect", "blocker", "testing", "test case", "sign off", "sign-off",
]

# Matched with word boundaries and an optional plural. Substring matching gives
# nonsense - "hr" inside "through", "check" inside "checking".
PATTERNS = [(t, re.compile(r"\b" + re.escape(t) + r"s?\b")) for t in GLOSSARY]

SPEAKER = re.compile(r"^([A-Z][^:]{1,40}):\s*(.*)$")


def profile(path, min_count, max_terms, max_speakers):
    lines = open(path, encoding="utf-8", errors="replace").read().splitlines()
    cues = [ln for ln in lines if "-->" in ln]
    length = cues[-1].split("-->")[1].strip().split(".")[0] if cues else "?"

    speakers = collections.Counter()
    said = []
    for ln in lines:
        if "-->" in ln:
            continue
        m = SPEAKER.match(ln)
        if m:
            speakers[m.group(1)] += 1
            said.append(m.group(2).lower())

    text = " ".join(said)
    hits = sorted(((len(p.findall(text)), t) for t, p in PATTERNS), reverse=True)
    hits = [(c, t) for c, t in hits if c >= min_count][:max_terms]

    return {
        "file": os.path.basename(path),
        "length": length,
        "cues": len(cues),
        "speakers": [s for s, _ in speakers.most_common(max_speakers)],
        "terms": [(t, c) for c, t in hits],
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("folder", help="folder holding .vtt transcripts")
    ap.add_argument("--min-count", type=int, default=6,
                    help="ignore terms mentioned fewer times (default 6)")
    ap.add_argument("--max-terms", type=int, default=8)
    ap.add_argument("--max-speakers", type=int, default=6)
    args = ap.parse_args()

    paths = sorted(glob.glob(os.path.join(args.folder, "*.vtt")))
    if not paths:
        print(f"no .vtt files in {args.folder}")
        return

    for path in paths:
        p = profile(path, args.min_count, args.max_terms, args.max_speakers)
        terms = ", ".join(f"{t} ({c})" for t, c in p["terms"]) or "(no domain terms)"
        print(f"{p['file']} | {p['length']} | {'; '.join(p['speakers'])} | {terms}")


if __name__ == "__main__":
    main()
