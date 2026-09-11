#!/usr/bin/env python3
"""Look up expected access from the project's permissions matrix.

RUN this script - do not read the matrix into context. Only the output costs tokens.

    python scripts/lookup_permission.py --role "User L2" --feature "View pricing"
    python scripts/lookup_permission.py --feature "Place order"        # every role
    python scripts/lookup_permission.py --role Admin --section "My Account"
    python scripts/lookup_permission.py --list-roles

Matrix format
-------------
Rows are features, columns are roles. First two columns are Section and Feature;
every remaining column is a role.

CSV : the cell text is the verdict, e.g. "Allowed", "Not Allowed", "Not Applicable",
      optionally with a scope after a colon: "Allowed: own only".

XLSX: the same, and additionally - if a cell is blank but filled with a colour - the
      fill colour is used as the verdict via COLOUR_VERDICTS below. Colour-coded
      matrices are common when the sheet is maintained by non-engineers.

Point --matrix at your own file; the default is the example shipped with this workspace.
"""
import argparse
import csv
import os
import sys
import io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_MATRIX = os.path.normpath(
    os.path.join(HERE, "..", "..", "..", "..",
                 "knowledge-base", "reference-data", "permissions-matrix.csv"))

# Fill colour -> verdict, for colour-coded spreadsheets. Adjust to your sheet's palette.
COLOUR_VERDICTS = {
    "FF93C47D": "Allowed",
    "FFEA9999": "Not Allowed",
    "FFB7B7B7": "Not Applicable",
}

SECTION_COL, FEATURE_COL = 0, 1


def load_csv(path):
    with open(path, newline="", encoding="utf-8-sig") as fh:
        rows = list(csv.reader(fh))
    if not rows:
        sys.exit(f"{path} is empty.")
    return rows[0], [r for r in rows[1:] if any(c.strip() for c in r)]


def load_xlsx(path):
    try:
        import openpyxl
    except ImportError:
        sys.exit("Reading .xlsx needs openpyxl:  pip install openpyxl")
    ws = openpyxl.load_workbook(path, data_only=True).active
    grid = list(ws.iter_rows())
    header = [(c.value or "") for c in grid[0]]
    rows = []
    for cells in grid[1:]:
        if not any(c.value for c in cells[:2]):
            continue
        out = []
        for c in cells:
            text = str(c.value).strip() if c.value is not None else ""
            if not text and c.fill is not None and c.fill.patternType == "solid":
                text = COLOUR_VERDICTS.get(c.fill.fgColor.rgb, "")
            out.append(text)
        rows.append(out)
    return header, rows


def load(path):
    if not os.path.exists(path):
        sys.exit(f"Matrix not found: {path}\nPass --matrix with the path to yours.")
    return load_xlsx(path) if path.lower().endswith((".xlsx", ".xlsm")) else load_csv(path)


def split_verdict(cell):
    """'Allowed: own only' -> ('Allowed', 'own only')"""
    cell = (cell or "").strip()
    if not cell:
        return "Unspecified", ""
    if ":" in cell:
        verdict, scope = cell.split(":", 1)
        return verdict.strip(), scope.strip()
    return cell, ""


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--matrix", default=DEFAULT_MATRIX, help="Path to the matrix (.csv or .xlsx)")
    ap.add_argument("--role", help="Role column name (exact, or a unique substring)")
    ap.add_argument("--feature", help="Substring of the Feature column")
    ap.add_argument("--section", help="Substring of the Section column")
    ap.add_argument("--list-roles", action="store_true")
    a = ap.parse_args()

    header, rows = load(a.matrix)
    roles = {h.strip(): i for i, h in enumerate(header) if i > FEATURE_COL and str(h).strip()}

    if a.list_roles:
        print(f"Matrix: {a.matrix}\n\nRoles ({len(roles)}):")
        for r in roles:
            print("  -", r)
        return

    if not (a.feature or a.section):
        sys.exit("Give --feature and/or --section (or --list-roles). See --help.")

    targets = roles
    if a.role:
        exact = [r for r in roles if r.lower() == a.role.lower()]
        partial = [r for r in roles if a.role.lower() in r.lower()]
        match = exact or partial
        if not match:
            sys.exit(f"Unknown role '{a.role}'. Known: {', '.join(roles)}")
        if len(match) > 1:
            sys.exit(f"'{a.role}' is ambiguous: {', '.join(match)}")
        targets = {match[0]: roles[match[0]]}

    hits = [r for r in rows
            if (not a.feature or a.feature.lower() in str(r[FEATURE_COL]).lower())
            and (not a.section or a.section.lower() in str(r[SECTION_COL]).lower())]

    if not hits:
        sys.exit("No matching rows. Try a shorter --feature substring, or --list-roles.")

    for row in hits:
        print(f"\n{row[SECTION_COL]} > {row[FEATURE_COL]}")
        for role, idx in targets.items():
            verdict, scope = split_verdict(row[idx] if idx < len(row) else "")
            line = f"  {role:34} {verdict}"
            if scope:
                line += f"   [scope: {scope}]"
            elif verdict == "Allowed":
                line += "   [no scope restriction]"
            print(line)

    print("\nThis is the documented baseline. Verify it against the live permission "
          "configuration before testing - the two drift.")


if __name__ == "__main__":
    main()
