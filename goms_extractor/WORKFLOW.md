# GOMS Extractor Workflow - Quick Reference

## Pipeline Flow

```
┌─────────────────────────────────────────────────────────────────┐
│                    INPUT: Multi-GO PDF                          │
│                  (e.g., combined_gos.pdf)                       │
└────────────────────────────┬────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│                    STEP 1: GO SPLITTER                          │
│                    (splitter.py)                                │
│                                                                 │
│  • Uses Gemini to identify GO boundaries                       │
│  • Splits into individual PDF files                            │
│  • Output: outputs/split_goms/                                 │
│    - GO_464_Pages_1-5.pdf                                      │
│    - GO_465_Pages_6-10.pdf                                     │
│    - GO_466_Pages_11-15.pdf                                    │
└────────────────────────────┬────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│                STEP 2: MARKDOWN CONVERTER                       │
│                  (md_converter.py)                              │
│                                                                 │
│  • Converts each GO PDF to markdown                            │
│  • Uses Gemini multimodal API                                  │
│  • Preserves document structure                                │
│  • Output: outputs/markdown_goms/                              │
│    - GO_464_Pages_1-5.md                                       │
│    - GO_465_Pages_6-10.md                                      │
│    - GO_466_Pages_11-15.md                                     │
└────────────────────────────┬────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│                STEP 3: AMENDMENT PARSER                         │
│                    (parser.py)                                  │
│                                                                 │
│  • Reads markdown files                                        │
│  • Extracts GO metadata                                        │
│  • Parses amendments with Gemini                               │
│  • Structures data into GoDocument objects                     │
│  • Output: outputs/parsed_goms/                                │
│    - GO_batch_amendments.json                                  │
│    - GO_batch_amendments.md                                    │
└────────────────────────────┬────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│                    OUTPUT: Structured Data                      │
│                                                                 │
│  JSON: Machine-readable amendment data                         │
│  MD:   Human-readable formatted report                         │
└─────────────────────────────────────────────────────────────────┘
```

## Key Functions

| Module | Function | Input | Output |
|--------|----------|-------|--------|
| `splitter.py` | `split_goms()` | Multi-GO PDF path | Dict with split PDF paths |
| `md_converter.py` | `convert_split_gos_to_markdown()` | Split result dict | Dict with markdown paths |
| `tools.py` | `parse_amendments_from_markdown()` | List of markdown paths | Dict with parsed documents |

## Quick Start

### Using the Agent (Automatic)
```python
from goms_extractor.agent import root_agent
result = root_agent.run("Process /path/to/multi_go.pdf")
```

### Manual Workflow
```python
from goms_extractor.splitter import split_goms
from goms_extractor.md_converter import convert_split_gos_to_markdown
from goms_extractor.tools import parse_amendments_from_markdown

# Chain the functions
split_result = split_goms("input.pdf")
md_result = convert_split_gos_to_markdown(split_result)
parse_result = parse_amendments_from_markdown(md_result['markdown_files'])
```

### Test Script
```bash
python test_markdown_workflow.py /path/to/multi_go.pdf
```

## Data Flow

```
split_goms()
    ↓ returns
{
  "split_files": ["GO_464.pdf", "GO_465.pdf"],
  "go_index": [...]
}
    ↓ passed to
convert_split_gos_to_markdown()
    ↓ returns
{
  "markdown_files": ["GO_464.md", "GO_465.md"],
  "conversion_results": [...]
}
    ↓ markdown_files extracted and passed to
parse_amendments_from_markdown()
    ↓ returns
{
  "documents": [{GoDocument}, {GoDocument}],
  "output_files": ["output.json", "output.md"]
}
```

## Amendment Structure

Each amendment contains:
- **Position**: rule_no, sub_rule, clause, sub_clause, proviso_no
- **Action**: type_of_action (sub/omit/add)
- **Content**: target_text, updated_text
- **Metadata**: confidence, raw_amendment_text

## Why Markdown?

1. **Cleaner Processing**: No PDF parsing complexity
2. **LLM-Friendly**: Optimal format for Gemini
3. **Human-Readable**: Easy to inspect and debug
4. **Structured**: Preserves document hierarchy
5. **Cacheable**: Reuse without re-processing PDFs
