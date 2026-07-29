from fastapi import UploadFile, File, HTTPException, APIRouter
from pathlib import Path
import tempfile
import subprocess
import shutil
import asyncio
from src.llm.client import LLMClient
from src.agents.critique.api.services.extraction_schema import SignOffSection, PrerequisitesSection, TaskAssignmentsSection, EventDescriptionSection
import logging

llm_client = LLMClient()
logger = logging.getLogger(__name__)

async def convert_docx_to_pdf(docx_path: Path) -> Path:
    """
    Convert DOCX → PDF using LibreOffice installed in the container.
    Returns path to generated PDF.
    """
    if not docx_path.exists():
        raise FileNotFoundError(f"File not found: {docx_path}")

    def _convert() -> Path:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)

            input_docx = tmpdir / docx_path.name
            input_docx.write_bytes(docx_path.read_bytes())

            subprocess.run(
                [
                    "soffice",
                    "--headless",
                    "--nologo",
                    "--nodefault",
                    "--nofirststartwizard",
                    "--convert-to", "pdf",
                    "--outdir", str(tmpdir),
                    str(input_docx),
                ],
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )

            pdf_path = tmpdir / (docx_path.stem + ".pdf")
            if not pdf_path.exists():
                raise RuntimeError("PDF not generated")

            final_pdf = docx_path.with_suffix(".pdf")
            final_pdf.write_bytes(pdf_path.read_bytes())
            return final_pdf

    return await asyncio.to_thread(_convert)


system_prompt = """
You are a pharmaceutical regulatory document extraction engine.

You process GMP Root Cause Investigation (RCI) / Investigation Plan documents
used in regulated pharmaceutical environments.

NON‑NEGOTIABLE RULES:
- Extract information EXACTLY as written in the document
- All dates must be in the format of "DD-MM-YYYY"
- Do NOT infer, assume, deduce, normalize, or correct anything
- Do NOT transform wording, spelling, punctuation, units, or formats
- Do NOT summarize, explain, interpret, or add context
- If a value is missing, blank, unchecked, or unclear → return null
- If text says "NA", "-", or is empty → return exactly as written
- Never merge information across rows, tables, or sections
- Preserve row order and section boundaries
- Tables must be interpreted row‑by‑row, cell‑by‑cell

BOOLEAN RULES:
- Checkbox / tick fields are TRUE only if an explicit checkmark, tick, √,
  or clearly marked selection is present in that row
- If a checkbox cell is blank → selected = false
- Never infer a tick based on surrounding text

SCOPE RULES:
- Extract ONLY from the section explicitly requested
- Ignore all other sections even if related
- If a table or text does not belong to the requested section → ignore it

Date rules:
- Extract dates exactly as written into *_raw fields
- Convert dates to ISO format (YYYY-MM-DD) only when unambiguous
- If date format is unclear, set normalized date field to null
- Never guess or reformat raw text

Checkbox rule:
- Even if multiple checkmarks appear visually, select ONLY ONE final answer
- If an explanation states “Not Applicable”, choose N/A
- If Yes and N/A are both marked, N/A takes precedence
- Never return more than one selected value for a prerequisite

OUTPUT RULES:
- Output must strictly follow the provided response schema
- Do not add extra keys, comments, or explanations
- Output must be suitable for regulatory audit and inspection
""".strip()



# ------------------------------------------------------------
# Section-specific extractors
# ------------------------------------------------------------

async def extract_section_11(file_id: str):
    logger.info("extracting section 1.1")

    return await llm_client.get_structured_response_from_file(
        file_id=file_id,
        system_prompt=system_prompt,
        user_prompt="""
Extract SECTION 1.1 – Event Description ONLY.

OUTPUT FORMAT REQUIREMENTS:
- Use the provided schema.
- After the RCI header, ALL extracted content MUST be placed inside a list called `sections`.
- Each item in `sections` MUST contain:
  - section_type (string)
  - title (if present in document)
  - content (object)

From this section extract:

1. RCI header table values:
   - RCI Number
   - RCI Owner
   - RCI Initiated on (must be in the format DD-MM-YYYY)
   - Parent record (include reference number and date if present)

2. Variable sub-sections (add each as a separate item in `sections`):
   - Problem statement narrative
   - Embedded tables inside the problem statement
   - Reported results
   - Observation details
   - Other details
   - QA notification

Rules for `sections`:
- section_type should be a logical identifier (e.g. "problem_statement", "observation_details")
- content MUST preserve text exactly as written
- Preserve bullet points, headings, and table rows
- All dates must be in the format of "DD-MM-YYYY"
- Do NOT summarize, rephrase, infer, or normalize values
- Do NOT merge tables or rows
- Do NOT omit narrative text
- Do NOT extract content from other sections
""".strip(),
        structure=EventDescriptionSection,
    )


async def extract_section_12(file_id: str):
    logger.info("extracting section 1.2")
    return await llm_client.get_structured_response_from_file(
        file_id=file_id,
        system_prompt=system_prompt,
        user_prompt="""
Extract SECTION 1.2 – Pre‑requisite of Investigation Plan ONLY.

This section contains a table listing investigation prerequisites.
Do NOT extract content from any other section.

For EACH table row extract the following fields:

- sr_number:
  - Extract the serial number EXACTLY as written
  - Preserve numbering format (e.g., 1, 1., 01, etc.)

- prerequisite:
  - Extract the prerequisite text EXACTLY as written
  - Preserve spelling, punctuation, symbols, and line breaks
  - Do NOT rewrite, clean, or summarize

- yes_selected (true/false):
  - true ONLY if the symbol immediately preceding "Yes" is "" or ""
  - Otherwise false

- no_selected (true/false):
  - true ONLY if the symbol immediately preceding "No" is "" or ""
  - Otherwise false

- na_selected (true/false):
  - true ONLY if the symbol immediately preceding "N/A" is "" or ""
  - If N/A option does not appear in the row, set na_selected = false
  - Otherwise false

Checkbox selection rules (CRITICAL)
- "" and "" = explicitly selected option
- "" and "•" = not selected
- The option label (Yes / No / N/A) determines the value.
- A selection is true ONLY when the symbol immediately preceding that option is "" or "".
- "", "•", empty cell, or any other symbol = false for that option.
- If options are shown (e.g., "Yes  No  N/A") but no option is explicitly marked with "" or "", then all options are false.
- If the marking is unclear, ambiguous, or more than one option appears selected in the same row, then all options are false.
- Do not infer selections from explanation text or context.
- Do not assume that exactly one option must be selected unless it is explicitly marked.

- explanation:
  - Extract the explanation text EXACTLY as written
  - Preserve punctuation, spacing, and line breaks
  - Preserve values such as "NA", "-", or blank cells exactly as shown
  - Do NOT interpret, normalize, or summarize

Rules (STRICT):
- Preserve row order EXACTLY as it appears in the table
- Do NOT merge rows
- Allow for any number of additional rows without changing extraction logic
- Do NOT infer compliance, intent, or justification
- Do NOT convert placeholders (NA, -, blank) to null
- Extract ONLY SECTION 1.2
- Ignore all other sections completely
""".strip(),
        structure=PrerequisitesSection,
    )


async def extract_section_21(file_id: str):
    logger.info("extracting section 2.1")
    return await llm_client.get_structured_response_from_file(
        file_id=file_id,
        system_prompt=system_prompt,
        user_prompt="""Extract SECTION 2.1 – Identification of Investigation Team members & Task Assignment ONLY.

This section contains a single task assignment table and a SIDE HINT that defines
how mandatory tasks are identified.

This section contains the following EXACT task rows
(in this exact order, no additions, no deletions):

1. Batch manufacturing records
2. Batch Packing Records
3. Analytical/Test Data
4. Instrument /Equipment Logbook
5. Calibration records
6. Preventive Maintenance records
7. Breakdown history
8. Training records
9. Environmental monitoring records
10. Records/Trends of various utilities used
11. Stability data
12. Product development reports
13. Process Validation records
14. Standard operating procedures
15. Annual product review for the past 2 APQR’s
16. Cleaning Validation Records
17. Standard Test Procedure
18. Pharmacopeia/ Vendor Test Method
19. Analyst qualification/Trend of analyst
20. Qualification records
21. Analytical Method Validation Records
22. Analytical method: Transfer records
23. Additional interview
24. Scope: Other products/processes
25. Complaint sample evaluation
26. Retain Sample Evaluation
27. CAPA History and Effectiveness Check
28. Event History
29. Number of Batches manufactured in the past 2 years of the affected product
30. Review of ongoing global CAPA related to similar failure (implementation at the respective site)
31. Others (Specify)

IMPORTANT SIDE HINT (located outside the table):
- The items prefixed with a specific marker are mandatory in all investigations.

For EACH row extract:

- selected (true/false):
  - true ONLY if the first column contains an explicit selected marker ("" or "")
  - "•", empty cell, "", or any other symbol = false
  - If the mark is unclear or ambiguous, set selected = false
  - At most one selected marker will be present

- task_name:
  - Extract task text EXACTLY as written in the table
  - Preserve spacing, punctuation, symbols, and case
  - Preserve any leading prefix or marker exactly as shown

- remarks:
  - Extract the full text from the remarks / verification column EXACTLY
  - Preserve full sentences, bullet points, and line breaks
  - Values such as "Verified", "Shall be verified",
    "The historical event shall be verified." must be kept verbatim
  - If the cell value is "Not Applicable", return exactly "Not Applicable"

- responsible_person:
  - Extract the name EXACTLY as written
  - If the cell value is "Not Applicable", return exactly "Not Applicable"
  - If the cell is truly blank, return a blank value

mandatory flag:
- Determine mandatory using the SIDE HINT ONLY
- Identify the marker/prefix described in the side hint
- If the task_name starts with that identified marker/prefix, set mandatory = true
- Otherwise set mandatory = false
- Do NOT assume or hard‑code any specific symbol
- Do NOT infer mandatory status using ticks, bullets, or verification text

Rules (STRICT):
- Preserve row order EXACTLY as listed
- Do NOT merge rows
- Do NOT infer responsibility
- Do NOT normalize task names, remarks, or symbols
- Do NOT convert "Not Applicable" to null
- Only extract SECTION 2.1
- Ignore all other sections completely
""".strip(),
        structure=TaskAssignmentsSection,
    )


async def extract_section_22(file_id: str):
    logger.info("extracting section 2.2")
    return await llm_client.get_structured_response_from_file(
        file_id=file_id,
        system_prompt=system_prompt,
        user_prompt="""
Extract SECTION 2.2 – RCI Plan Sign‑off ONLY.

From the sign‑off table extract:
- All sign‑off role titles exactly as written
- Corresponding signatory names exactly as written

Rules:
- Include ALL roles even if name is blank or NA
- Preserve role labels (Investigation Writer, Task owner, QA reviewer, etc.)
- usually the roles will be present first and the list of names follow the list of roles
- the roles and the names are separated by "-" sign
- Try to map the role to the name based on th order of role and name
- Do NOT normalize role names
- Do NOT infer missing signatories
- Do NOT extract signatures from outside this table
""".strip(),
        structure=SignOffSection,
    )


# ------------------------------------------------------------
# Merge function
# ------------------------------------------------------------

def merge_sections(s11, s12, s21, s22):
    return {
        "EventDescription": s11.model_dump(mode="json"),
        "prerequisites": s12.model_dump(mode="json"),
        "taskassignments": s21.model_dump(mode="json"),
        "signoff": s22.model_dump(mode="json"),
    }
