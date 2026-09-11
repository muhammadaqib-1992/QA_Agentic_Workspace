# Matrix Guide

Reference for `qa-permission-testing`. **Only load this when you need to read the permissions matrix by hand** — for an ordinary lookup, run `scripts/lookup_permission.py`, which resolves all of this for you.

## Expected shape

Rows are features, columns are roles:

| Column | Contents |
|---|---|
| 1 — `Section` | Grouping (General, Shopping, Checkout, My Account, Admin…) |
| 2 — `Feature` | The page, action or capability being governed |
| 3+ | One column per role. The header is the role name |

`knowledge-base/reference-data/permissions-matrix.csv` is a working example of this shape.

## Verdicts

| Value | Meaning |
|---|---|
| `Allowed` | Fully permitted, no scope restriction |
| `Allowed: <scope>` | Permitted, but limited to the records described by the scope |
| `Not Allowed` | Must be blocked |
| `Not Applicable` | The combination is meaningless for this role — not a test scenario |
| *(empty)* | **Unspecified — a gap, not a permission.** Flag it; don't infer |

Common scopes: `own only`, `own + parent`, `own + assigned accounts`, `read only`.

That last row matters. A blank cell means nobody decided, and the right response is to say so — not to assume the safest-sounding option. Guessing here produces test cases that enforce a rule the team never agreed to.

## Colour-coded spreadsheets

Matrices maintained by non-engineers often carry the verdict as a **fill colour** with the cell text blank, or as colour *plus* a scope note. The script handles this for `.xlsx` via its `COLOUR_VERDICTS` map — adjust that map to your sheet's palette.

Reading such a sheet by hand is error-prone in a specific way: an allowed cell is very often *empty*, so scanning the text alone makes permissions look undefined when they are in fact granted. The fill colour must be read programmatically (`cell.fill.fgColor.rgb`); it cannot be inferred from the value. This is the main reason the script exists.

## Role applicability

Roles frequently do not apply everywhere — a role may exist only on one product line, brand, or tenant. If your matrix encodes that (a header row of applicable products, or a `Not Applicable` verdict), respect it: testing a role against a product it does not exist on is a non-scenario, not a failure.

## When the matrix and the application disagree

That disagreement is a finding in its own right, and which way it points changes what you file:

- **Application is more permissive than the matrix** → potential security defect. Treat it as high priority.
- **Application is more restrictive** → likely a functional defect, or the matrix is out of date.
- **Live admin config differs from the matrix** → the documentation is stale. Worth a note even when behaviour is correct, because the matrix is what the next person will test against.
