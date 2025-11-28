# GOMS Extractor - Markdown-Based Workflow

## Overview

The GOMS Extractor processes Government Order (GO) documents through a three-stage pipeline:

1. **Split PDFs** - Split multi-GO PDFs into individual GO PDF files
2. **Convert to Markdown** - Convert each GO PDF to markdown format
3. **Parse Amendments** - Extract structured amendment data from markdown files

## Architecture

```
Input PDF (Multiple GOs)
         ↓
    [Splitter]
         ↓
Individual GO PDFs
         ↓
  [MD Converter]
         ↓
Individual GO Markdown Files
         ↓
 [Amendment Parser]
         ↓
Structured Amendment Data (JSON + MD)
```

## Key Components

### 1. Splitter (`splitter.py`)

**Function:** `split_goms(input_pdf_path, output_dir=None)`

Splits a PDF containing multiple GOs into individual PDF files.

**Input:**
- `input_pdf_path`: Path to PDF with multiple GOs

**Output:**
```python
{
    "status": "success|error",
    "message": "Description",
    "split_files": ["path/to/GO_464.pdf", "path/to/GO_465.pdf", ...],
    "go_index": [{"goms_no": "464", "start_page": 0, "end_page": 5}, ...]
}
```

**Output Location:** `outputs/split_goms/`

### 2. Markdown Converter (`md_converter.py`)

**Function:** `convert_split_gos_to_markdown(split_result)`

Converts split GO PDFs to markdown format using Gemini's multimodal API.

**Input:**
- `split_result`: Output from `split_goms()`

**Output:**
```python
{
    "status": "success|error",
    "message": "Description",
    "markdown_files": ["path/to/GO_464.md", "path/to/GO_465.md", ...],
    "conversion_results": [...]
}
```

**Output Location:** `outputs/markdown_goms/`

**Why Markdown?**
- Easier text processing (no PDF parsing complexity)
- Better for LLM context (structured text)
- Human-readable intermediate format
- Preserves document structure

### 3. Amendment Parser (`parser.py`)

**Class:** `EnhancedGoAmendmentParser`

**Key Methods:**

#### `parse_markdown_file(markdown_path: str) -> GoDocument`
Parses a single GO markdown file and extracts amendments.

**Input:**
- `markdown_path`: Path to a GO markdown file

**Output:**
- `GoDocument` object with structured amendment data

#### `parse_go(go_text: str) -> GoDocument`
Core parsing logic that works with text (markdown or plain text).

**Extracts:**
- GO metadata (number, abstract, references, signatures)
- Individual amendments with:
  - Rule/sub-rule/clause/sub-clause hierarchy
  - Type of action (substitute, omit, add)
  - Target text (being replaced/deleted)
  - Updated text (new content)
  - Confidence level (high/medium/low)

### 4. Tools (`tools.py`)

**Function:** `parse_amendments_from_markdown(markdown_files: list)`

Batch processes multiple markdown files and exports results.

**Input:**
- `markdown_files`: List of markdown file paths

**Output:**
```python
{
    "status": "success|error",
    "message": "Description",
    "documents": [...],  # Serialized GoDocument objects
    "output_files": ["path/to/output.json", "path/to/output.md"]
}
```

**Output Location:** `outputs/parsed_goms/`

## Data Models

### Amendment
```python
@dataclass
class Amendment:
    rule_no: str                          # e.g., "Rule 12"
    sub_rule: Optional[str]               # e.g., "sub-rule (1)"
    clause: Optional[str]                 # e.g., "clause (a)"
    sub_clause: Optional[str]             # e.g., "sub-clause (i)"
    proviso_no: Optional[str]             # e.g., "first proviso"
    additional_position_ctx: Optional[str] # Additional context
    type_of_action: str                   # "sub", "omit", or "add"
    target_text: Optional[str]            # Text being replaced/deleted
    updated_text: Optional[str]           # New text being added
    raw_amendment_text: str               # Original full text
    confidence: str                       # "low", "medium", "high"
```

### GoDocument
```python
@dataclass
class GoDocument:
    goms_no: str                    # e.g., "G.O.Ms.No.464"
    abstract: str                   # Subject/abstract
    references: List[str]           # Referenced documents
    notification: str               # Notification content
    amendment: List[Amendment]      # List of amendments
    signed_by: str                  # Signatory name and designation
    signed_to: str                  # Recipients
    raw_text: str                   # Complete original text
```

## Usage

### Option 1: Using the Agent Workflow (Recommended)

The agent automatically orchestrates all three steps:

```python
from goms_extractor.agent import root_agent

# The agent handles: split → convert → parse → report
result = root_agent.run("Process this PDF: /path/to/multi_go.pdf")
```

### Option 2: Manual Step-by-Step

```python
from goms_extractor.splitter import split_goms
from goms_extractor.md_converter import convert_split_gos_to_markdown
from goms_extractor.tools import parse_amendments_from_markdown

# Step 1: Split
split_result = split_goms("/path/to/multi_go.pdf")

# Step 2: Convert to markdown
md_result = convert_split_gos_to_markdown(split_result)

# Step 3: Parse amendments
parse_result = parse_amendments_from_markdown(md_result['markdown_files'])

print(f"Processed {len(parse_result['documents'])} GOs")
print(f"Output: {parse_result['output_files']}")
```

### Option 3: Using the Test Script

```bash
python test_markdown_workflow.py /path/to/multi_go.pdf
```

### Option 4: Parse a Single Markdown File

```python
from goms_extractor.parser import EnhancedGoAmendmentParser

parser = EnhancedGoAmendmentParser()
go_doc = parser.parse_markdown_file("/path/to/GO_464.md")

print(f"GO: {go_doc.goms_no}")
print(f"Amendments: {len(go_doc.amendment)}")
```

## Output Files

### JSON Output (`*_amendments.json`)
Structured data suitable for programmatic processing:
```json
[
  {
    "goms_no": "G.O.Ms.No.464",
    "abstract": "...",
    "amendment": [
      {
        "rule_no": "Rule 12",
        "type_of_action": "sub",
        "target_text": "...",
        "updated_text": "...",
        "confidence": "high"
      }
    ]
  }
]
```

### Markdown Output (`*_amendments.md`)
Human-readable report with formatted amendments:
```markdown
## G.O.Ms.No.464

**Abstract:** ...

### Amendments (3)

#### Amendment 1 🟢
- **Rule:** Rule 12
- **Action:** sub
- **Confidence:** high
- **Target Text:** "..."
- **Updated Text:** "..."
```

## Directory Structure

```
goms/
├── goms_extractor/
│   ├── __init__.py
│   ├── agent.py              # ADK agent workflow
│   ├── splitter.py           # PDF splitting
│   ├── md_converter.py       # PDF → Markdown conversion
│   ├── parser.py             # Amendment extraction
│   ├── tools.py              # Tool functions for agents
│   └── models.py             # Data models
├── outputs/
│   ├── split_goms/           # Individual GO PDFs
│   ├── markdown_goms/        # Individual GO markdown files
│   └── parsed_goms/          # Final JSON + MD outputs
├── test_markdown_workflow.py # Test script
└── README.md
```

## Key Features

### 1. Markdown-First Approach
- **Cleaner pipeline**: Text processing instead of PDF parsing
- **Better debugging**: Inspect intermediate markdown files
- **LLM-friendly**: Markdown is optimal for Gemini processing

### 2. Gemini-Powered Extraction
- **Multimodal PDF processing**: Handles scanned documents
- **Intelligent parsing**: Understands legal document structure
- **High accuracy**: Extracts complex amendment hierarchies

### 3. Confidence Scoring
- **High**: Clear, unambiguous amendments
- **Medium**: Some ambiguity in extraction
- **Low**: Uncertain or complex amendments

### 4. Comprehensive Metadata
- Captures full document hierarchy (rule → sub-rule → clause → sub-clause → proviso)
- Preserves original text for verification
- Tracks action types (substitute, omit, add)

## Environment Setup

Required environment variables (`.env`):
```bash
GOOGLE_CLOUD_PROJECT=your-project-id
GOOGLE_APPLICATION_CREDENTIALS=/path/to/credentials.json
```

## Dependencies

```
google-adk
vertexai
pdfplumber
pypdf
python-dotenv
```

## Error Handling

Each stage returns a status dictionary:
- `status: "success"` - Operation completed successfully
- `status: "error"` - Operation failed (check `message` field)

Failed conversions/parses are logged but don't stop the pipeline.

## Performance Considerations

- **Batch processing**: Splitter processes pages in batches of 10
- **Rate limiting**: 10-second delay between Gemini batches
- **Parallel processing**: Independent GOs can be processed in parallel
- **Caching**: Markdown files serve as cache for re-parsing

## Future Enhancements

- [ ] Support for other document formats (DOCX, HTML)
- [ ] Parallel processing of markdown files
- [ ] Incremental updates (only process new GOs)
- [ ] Amendment validation against original rules
- [ ] Diff generation for before/after comparison
