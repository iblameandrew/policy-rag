"""Generate the dummy Acme Dynamics employee handbook PDF.

No third-party deps: writes a simple multi-page PDF that pypdf can extract
with heading-aware `# Section` lines for ingest/chunking.
"""

from __future__ import annotations

import argparse
import textwrap
from pathlib import Path

PAGE_WIDTH = 612  # US Letter
PAGE_HEIGHT = 792
MARGIN_LEFT = 54
MARGIN_TOP = 54
FONT_SIZE = 11
LEADING = 14
CHARS_PER_LINE = 92
LINES_PER_PAGE = 48

DOC_TITLE = "[TEST] EMPLOYEE HANDBOOK & POLICY MANUAL (DUMMY)"
DOC_SUBTITLE = "Acme Dynamics - Internal Use Only - Not real people"


def _handbook_sections() -> list[tuple[str, str]]:
    """Return (heading_line, body) pairs. Heading is stamped as `# ...`."""
    return [
        (
            "# 1. Welcome / Company Values",
            """
Acme Dynamics is a fictional company created for this take-home exercise.
Nothing in this document describes real people, real payroll, or real benefits.

Our values:
- Safety of employee data comes before convenience of internal tools.
- Ask HR through Workday or the HR shared inbox; do not ask chatbots for secrets.
- We default to least privilege. If you do not need a record, you do not see it.
- We write boring, correct systems and we prefer a refused answer to a leak.

This handbook is the source of truth for the PolicyRAG demo. Public sections
are readable by every authenticated role. Internal sections (compensation
philosophy) are limited to employees and above. The payroll appendix is
restricted to HR and Admin.

If a tool cannot ground an answer in a section you are allowed to read, the
correct answer is that it does not know.
""",
        ),
        (
            "# 2. Working Hours, PTO, and Remote Work",
            """
Working hours:
Core hours are 10:00 to 16:00 in the employee's local time zone, Monday
through Friday. Teams may agree on a 9-day fortnight only with manager
approval recorded in Workday.

Paid Time Off (PTO) policy:
Full-time employees accrue 15 days of PTO per calendar year, plus 10 paid
company holidays published on the intranet. Unused PTO may roll over up to
5 days into the next year. Requests under 3 consecutive days are approved
by the manager in Workday. Requests of 3 days or more should be submitted
at least two weeks in advance.

Sick time is separate: 6 days per year. Do not use PTO in place of sick
time when you are unwell.

Remote work:
Acme Dynamics is hybrid. Employees are expected on-site Tuesday through
Thursday unless their offer letter says otherwise. Monday and Friday are
optional work-from-home days. A stable internet connection is required for
remote days. Remote work is not a substitute for PTO.

Timekeeping:
Non-exempt employees must record hours in Workday daily. Exempt employees
record exceptions only (PTO, sick, jury duty).
""",
        ),
        (
            "# 3. Health Benefits Overview",
            """
This section is an overview. It contains no real protected health information
and no member-level claims data.

Medical:
Full-time employees may enroll in the Acme Dynamics group medical plan during
the first 30 days of employment or at open enrollment each November. Coverage
starts the first of the month after the employee elects a plan. Three dummy
tiers exist: Employee, Employee+Spouse, Family. Premiums are published in
Workday Benefits; this handbook does not list dollar amounts.

Dental and vision:
Dental and vision plans are optional add-ons. Waiting period is 0 days for
new hires who elect during onboarding.

Mental health:
The employee assistance program (EAP) offers 6 counseling sessions per
issue per year. The EAP phone number is listed on the intranet Benefits
page, not in this dummy PDF.

What this section does not contain:
No diagnosis lists, no claim IDs, no dependent Social Security Numbers, and
no explanation-of-benefits samples.
""",
        ),
        (
            "# 4. Compensation Philosophy",
            """
Classification: internal. This section describes how we think about pay. It
does not name any employee and it does not list anyone's actual salary.

Pay bands (DUMMY, not real offers):
- Band A (early career IC): USD 70,000 to 95,000
- Band B (mid IC): USD 95,000 to 130,000
- Band C (senior IC): USD 130,000 to 175,000
- Band M (people manager): USD 140,000 to 190,000

We target the 50th to 60th percentile of a blended tech market survey.
Location differentials may apply. Annual reviews occur in March. Merit
increases, if any, are effective in April payroll.

Equity:
Dummy restricted stock units may be granted at hire. Vesting is a 4-year
schedule with a 1-year cliff. Equity is not a substitute for base pay.

What managers may say:
Managers may discuss the band for an open role. Managers may not quote
another employee's salary, bonus, or payroll identifiers. Individual
compensation records live in the restricted payroll appendix and in the
HRIS. This philosophy section is not an authorization to retrieve those
records.
""",
        ),
        (
            "# 5. Appendix A - Payroll Examples (DUMMY)",
            """
RESTRICTED. Visible to HR and Admin roles only. This appendix exists ONLY
to prove the retrieval ACL. Every name, salary, and identifier below is
FAKE. Not real people. Not real bank accounts. Not real tax IDs.

Payroll examples (DUMMY / FAKE):

1) Alias user X / Jane Alvarez (FAKE)
   Department: Platform Engineering
   Annual salary: USD 87,400
   Bonus target: 8 percent
   SSN (FAKE, labeled FAKE): 078-05-1120
   Pay group: Biweekly US salaried

2) Alias user Y / Marcus Chen (FAKE)
   Department: Design
   Annual salary: USD 112,000
   Bonus target: 10 percent
   SSN (FAKE, labeled FAKE): 219-09-9999
   Pay group: Biweekly US salaried

3) Alias user Z / Priya Nair (FAKE)
   Department: People Operations
   Annual salary: USD 96,250
   Bonus target: 8 percent
   SSN (FAKE, labeled FAKE): 001-12-3456
   Pay group: Biweekly US salaried

4) Contractor example (FAKE)
   Name: Diego Ramos (FAKE)
   Day rate: USD 650
   SSN (FAKE, labeled FAKE): 456-78-9012
   Note: contractors are paid through the vendor system, not payroll.

If you can read this appendix through the assistant, your role filter is
hr or admin. Employees must never retrieve these rows. After ingest, raw
SSN digits must be replaced with [SSN_REDACTED] in the vector index.
Salary figures may remain for HR/Admin questions such as
"What is user X's salary?"
""",
        ),
        (
            "# 6. How to Request a Pay Stub",
            """
Process only. This section does not include pay amounts.

Employees request a pay stub in Workday:
1. Sign in to Workday with SSO.
2. Open Menu → Pay → Pay Documents (or search "payslip").
3. Select the pay date and download the PDF.
4. If a stub is missing after a new hire's first cycle, file an HR ticket
   with the pay date. Do not send bank account numbers in the ticket body.

Managers cannot download another person's stub. HR Partners can, through
the HRIS, not through this assistant.

The assistant may describe this process. The assistant may not attach a
stub, invent a net-pay figure, or read the payroll appendix for an
employee role.
""",
        ),
        (
            "# 7. IT / Acceptable Use",
            """
Company laptops are encrypted at rest. Use the password manager for
credentials. Do not reuse the SSO password on other sites.

Acceptable use:
- Software installs go through the company catalog.
- Customer data stays in approved SaaS tools.
- Do not paste production secrets, raw payroll files, or identification
  numbers into public AI products.
- RAG demos must keep embeddings local unless a written exception exists.

Phishing:
Report suspicious mail with the Report Phish button. IT will never ask for
your password or for a Social Security Number over chat.

Lost device:
Call the IT hotline on the intranet within 2 hours. Remote wipe is
standard.
""",
        ),
        (
            "# 8. Glossary",
            """
PTO: Paid Time Off. See section 2.

Workday: The dummy HRIS used in these examples.

Pay stub / payslip: A document showing gross pay, deductions, and net pay
for one cycle. Request it through Workday (section 6).

Compensation philosophy: How bands are set (section 4). Not a list of
named salaries.

Payroll appendix: Restricted dummy rows in section 5. HR and Admin only.

Classification public: Readable by public, employee, hr, and admin.

Classification internal: Readable by employee, hr, and admin.

Classification restricted: Readable by hr and admin only.

EAP: Employee Assistance Program. See section 3.

Least privilege: If a record is not needed for the task, it is not
retrieved. Authorization is enforced at retrieval time, not by asking the
language model to keep a secret.
""",
        ),
    ]


def handbook_plain_text() -> str:
    parts = [DOC_TITLE, DOC_SUBTITLE, ""]
    for heading, body in _handbook_sections():
        parts.append(heading)
        parts.append(textwrap.dedent(body).strip())
        parts.append("")
    return "\n".join(parts)


def _wrap_document_lines() -> list[str]:
    lines: list[str] = []
    for raw in handbook_plain_text().split("\n"):
        if raw == "":
            lines.append("")
            continue
        wrapped = textwrap.wrap(
            raw,
            width=CHARS_PER_LINE,
            replace_whitespace=False,
            drop_whitespace=False,
        ) or [""]
        lines.extend(wrapped)
    return lines


def _escape_pdf_literal(text: str) -> str:
    latin = text.encode("latin-1", "replace").decode("latin-1")
    return latin.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def _page_stream(page_lines: list[str]) -> bytes:
    y = PAGE_HEIGHT - MARGIN_TOP
    commands = [
        "BT",
        f"/F1 {FONT_SIZE} Tf",
        f"{MARGIN_LEFT} {y} Td",
    ]
    first = True
    for line in page_lines:
        if not first:
            commands.append(f"0 {-LEADING} Td")
        first = False
        commands.append(f"({_escape_pdf_literal(line)}) Tj")
    commands.append("ET")
    stream = "\n".join(commands) + "\n"
    return stream.encode("latin-1", "replace")


def build_pdf_bytes() -> bytes:
    all_lines = _wrap_document_lines()
    pages: list[list[str]] = []
    for i in range(0, len(all_lines), LINES_PER_PAGE):
        pages.append(all_lines[i : i + LINES_PER_PAGE])
    if not pages:
        pages = [[DOC_TITLE]]

    objects: list[bytes] = []

    def add_obj(body: bytes) -> int:
        objects.append(body)
        return len(objects)

    # 1: catalog, 2: pages, then 2 objects per page (page + content), then font
    add_obj(b"<< /Type /Catalog /Pages 2 0 R >>")
    add_obj(b"<< /Type /Pages /Kids [] /Count 0 >>")  # placeholder, patched later

    page_ids: list[int] = []
    content_ids: list[int] = []
    for page_lines in pages:
        stream = _page_stream(page_lines)
        content_id = add_obj(
            b"<< /Length "
            + str(len(stream)).encode("ascii")
            + b" >>\nstream\n"
            + stream
            + b"endstream"
        )
        content_ids.append(content_id)
        page_id = add_obj(b"%placeholder-page")
        page_ids.append(page_id)

    font_id = add_obj(b"<< /Type /Font /Subtype /Type1 /BaseFont /Courier /Encoding /WinAnsiEncoding >>")

    for page_id, content_id in zip(page_ids, content_ids, strict=True):
        objects[page_id - 1] = (
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 "
            + f"{PAGE_WIDTH} {PAGE_HEIGHT}".encode("ascii")
            + b"] /Contents "
            + f"{content_id} 0 R".encode("ascii")
            + b" /Resources << /Font << /F1 "
            + f"{font_id} 0 R".encode("ascii")
            + b" >> >> >>"
        )

    kids = " ".join(f"{pid} 0 R" for pid in page_ids)
    objects[1] = (
        f"<< /Type /Pages /Kids [{kids}] /Count {len(page_ids)} >>".encode("ascii")
    )

    out = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for idx, obj in enumerate(objects, start=1):
        offsets.append(len(out))
        out.extend(f"{idx} 0 obj\n".encode("ascii"))
        out.extend(obj)
        out.extend(b"\nendobj\n")
    xref_pos = len(out)
    out.extend(f"xref\n0 {len(objects) + 1}\n".encode("ascii"))
    out.extend(b"0000000000 65535 f \n")
    for off in offsets[1:]:
        out.extend(f"{off:010d} 00000 n \n".encode("ascii"))
    out.extend(
        (
            f"trailer << /Size {len(objects) + 1} /Root 1 0 R >>\n"
            f"startxref\n{xref_pos}\n%%EOF\n"
        ).encode("ascii")
    )
    return bytes(out)


def write_handbook(path: Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(build_pdf_bytes())
    return path


def main() -> None:
    parser = argparse.ArgumentParser(description="Write the dummy employee handbook PDF.")
    parser.add_argument(
        "--out",
        default=str(Path(__file__).resolve().parent.parent / "data" / "employee_handbook.pdf"),
        help="Output PDF path",
    )
    args = parser.parse_args()
    dest = write_handbook(Path(args.out))
    print(f"Wrote {dest} ({dest.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
