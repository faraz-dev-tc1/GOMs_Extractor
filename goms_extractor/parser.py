"""
Amendment parser for Government Orders (GOs).
Uses Vertex AI Gemini to improve extraction accuracy, especially for target_text and updated_text.
"""

import json
import os
import re
from datetime import datetime
from typing import List, Dict, Optional

from dotenv import load_dotenv
from vertexai.generative_models import GenerativeModel, GenerationConfig
import vertexai

from .models import Amendment, GoDocument


class GeminiAmendmentExtractor:
    """Uses Vertex AI Gemini to extract amendment details"""

    def __init__(self, project_id: str = None, location: str = "us-central1"):
        """
        Initialize Gemini API

        Args:
            project_id: GCP project ID (defaults to env var GOOGLE_CLOUD_PROJECT)
            location: GCP region
        """

        try:
            # Load environment variables from .env file
            # Use absolute path relative to this script's location
            script_dir = os.path.dirname(os.path.abspath(__file__))
            env_path = os.path.join(script_dir, '..', '.env')
            load_dotenv(env_path)

            # Fix path expansion issue: python-dotenv incorrectly prepends home directory
            # to /mnt/c paths in WSL environment
            creds_path = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
            if creds_path:
                # Check for incorrectly expanded WSL paths
                home_dir = os.path.expanduser("~")
                if creds_path.startswith(os.path.join(home_dir, "mnt", "c")):
                    # Remove the home directory prefix
                    creds_path = creds_path.replace(os.path.join(home_dir, "mnt", "c"), "/mnt/c", 1)
                    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = creds_path

            self.project_id = project_id or os.environ.get("GOOGLE_CLOUD_PROJECT")
            self.location = location

            if not self.project_id:
                print("WARNING: GOOGLE_CLOUD_PROJECT not set. Gemini extraction disabled.")
                self.enabled = False
                return

            self.enabled = True

            # Initialize Vertex AI
            vertexai.init(project=self.project_id, location=self.location)

            # Initialize Gemini model
            # Try different model names based on availability
            model_names = [
                'gemini-2.5-flash',
            ]

            model_initialized = False
            for model_name in model_names:
                try:
                    self.model = GenerativeModel(model_name)
                    # Test with a simple call to verify it works
                    print(f"✓ Using model: {model_name}")
                    model_initialized = True
                    break
                except Exception as e:
                    continue

            if not model_initialized:
                raise Exception("No Gemini model available. Please enable Vertex AI API.")

            # Generation config for structured output
            self.generation_config = GenerationConfig(
                temperature=0.1,  # Low temperature for factual extraction
                top_p=0.95,
                top_k=40,
                max_output_tokens=8192,
            )

            print(f"✓ Gemini API initialized (project: {self.project_id})")

        except Exception as e:
            print(f"WARNING: Failed to initialize Gemini: {e}")
            self.enabled = False

    def extract_amendment_details(self, amendment_text: str) -> Dict:
        """
        Use Gemini to extract detailed amendment information

        Args:
            amendment_text: The text of a single amendment

        Returns:
            Dict with extracted fields
        """
        if not self.enabled:
            return None

        prompt = f"""You are an expert legal document parser specializing in Indian Government Orders.

Extract detailed information from the following amendment text. Pay special attention to:
1. The exact rule being amended (e.g., "Rule 12", "Rule 22")
2. Sub-rule (e.g., "sub-rule (1)", "sub-rule (3)")
3. Clause (e.g., "clause (a)", "clause (b)")
4. Sub-clause (e.g., "sub-clause (i)", "sub-clause (ii)")
5. Proviso number if applicable (e.g., "first proviso", "second proviso")
6. Any additional position context (e.g., "the entire phrase specifying the position")
7. Type of action: "sub" (substitution), "omit" (deletion), "add" (insertion)
8. For SUBSTITUTIONS: Extract BOTH the target text (being replaced) AND the updated text
9. For INSERTIONS: Extract the updated text being added
10. For DELETIONS: Extract the target text being removed
11. As a fallback take the entire text written under Amendment section

AMENDMENT TEXT:
{amendment_text}

CRITICAL INSTRUCTIONS:
- Break down the position as granularly as possible (rule -> sub-rule -> clause -> sub-clause -> proviso)
- For substitutions, look for patterns like "for the words X, the words Y shall be substituted"
- The target_text is typically after "for the words" or "for clause"
- The updated_text is typically after "the following shall be substituted" or "the words X shall be substituted"
- Extract complete sentences/phrases, not fragments
- If text is in quotes, include the quotes
- If you cannot find a specific position element, set it to null

OUTPUT FORMAT:
Respond with ONLY a valid JSON object (no markdown, no explanations):
{{
  "rule_no": "Rule X",
  "sub_rule": "sub-rule (Y)" or null,
  "clause": "clause (Z)" or null,
  "sub_clause": "sub-clause (W)" or null,
  "proviso_no": "proviso number" or null,
  "additional_position_ctx": "the entire phrase specifying the position" or null,
  "type_of_action": "sub|omit|add",
  "target_text": "exact text being replaced/deleted (null if add)",
  "updated_text": "exact text being added/substituted (null if omit)",
  "confidence": "high|medium|low"
  "raw_amendment_text": "the entire text written under Amendment section"
}}

RESPOND WITH ONLY THE JSON OBJECT:"""

        try:
            response = self.model.generate_content(
                prompt,
                generation_config=self.generation_config,
            )

            response_text = response.text.strip()

            # Clean up response (remove markdown code blocks if present)
            response_text = response_text.replace("```json", "").replace("```", "").strip()

            # Parse JSON
            result = json.loads(response_text)
            return result

        except json.JSONDecodeError as e:
            print(f"WARNING: Failed to parse Gemini response as JSON: {e}")
            print(f"Response: {response_text[:200]}...")
            return None
        except Exception as e:
            print(f"WARNING: Gemini extraction failed: {e}")
            return None

    def extract_go_metadata(self, text: str) -> Dict:
        """
        Use Gemini to extract GO metadata (header information)
        """
        if not self.enabled:
            return None

        prompt = f"""Extract structured data from this Government Order document.

DOCUMENT TEXT:
{text}

Extract the following fields:
1. GOMs No: The Government Order Manuscript Number (e.g., "G.O.Ms.No.464")
2. Abstract: The abstract or subject of the order
3. Notification: The content of the notification section (if present)
4. Signed_by: The name and designation of the person signing the order (usually at the bottom)
5. Signed_to: The recipients listed in the "To" section

RESPOND WITH ONLY A JSON OBJECT:
{{
  "goms_no": "G.O.Ms.No.XXX",
  "abstract": "Abstract text",
  "notification": "Notification text or null",
  "signed_by": "Name, Designation",
  "signed_to": "Recipient list or null"
}}"""

        try:
            response = self.model.generate_content(
                prompt,
                generation_config=self.generation_config,
            )

            response_text = response.text.strip()
            response_text = response_text.replace("```json", "").replace("```", "").strip()

            result = json.loads(response_text)
            return result

        except Exception as e:
            print(f"WARNING: Gemini metadata extraction failed: {e}")
            return None


class EnhancedGoAmendmentParser:
    """Enhanced parser with Gemini API integration"""

    def __init__(self, use_gemini: bool = True, project_id: str = None):
        """
        Initialize parser

        Args:
            use_gemini: Whether to use Gemini API (requires credentials)
            project_id: GCP project ID (optional, uses env var if not provided)
        """
        # Regex patterns (fallback)
        self.go_number_pattern = r'G\.O\.Ms\.No\.?\s*(\d+)'
        self.date_pattern = r'Dated[:\s]+(\d{1,2}[-/]\d{1,2}[-/]\d{4})'
        self.rule_pattern = r'[Rr]ule[-\s]*(\d+[A-Z]?(?:\([^)]+\))*)'

        # Initialize Gemini extractor
        self.gemini = None
        if use_gemini:
            self.gemini = GeminiAmendmentExtractor(project_id=project_id)
            if not self.gemini.enabled:
                print("Falling back to regex-only mode")
                self.gemini = None

    def extract_text_from_pdf(self, pdf_path: str) -> str:
        """Extract text from PDF file using Gemini's multimodal API (no fallback)."""
        if not self.gemini or not self.gemini.enabled:
            raise RuntimeError("Gemini extractor is not enabled; cannot extract PDF text.")

        # Use Gemini for PDF extraction (handles scanned PDFs)
        from vertexai.generative_models import Part

        print("  Extracting text with Gemini...", end="", flush=True)

        # Read PDF as bytes
        with open(pdf_path, "rb") as f:
            pdf_data = f.read()

        # Create PDF part
        pdf_part = Part.from_data(pdf_data, mime_type="application/pdf")

        prompt = """Extract ALL text from this PDF document.
Return the complete text content exactly as it appears, preserving formatting and structure.
Do not summarize or skip any content."""

        response = self.gemini.model.generate_content([prompt, pdf_part])
        print(" ✓")
        return response.text

    def split_into_gos(self, text: str) -> List[str]:
        """Split a large document into individual GOs"""
        go_splits = re.split(
            r'(?=GOVERNMENT OF ANDHRA PRADESH\s+ABSTRACT)',
            text,
            flags=re.IGNORECASE
        )
        gos = [go.strip() for go in go_splits if go.strip()]
        return gos

    def parse_go_header_regex(self, text: str) -> Dict[str, str]:
        """Extract GO header using regex (fallback method)"""
        header_info = {
            'go_number': '',
            'date': '',
            'department': '',
            'subject': '',
            'effective_date': None
        }

        # Extract GO number
        go_match = re.search(self.go_number_pattern, text)
        if go_match:
            header_info['go_number'] = f"G.O.Ms.No.{go_match.group(1)}"

        # Extract date
        date_match = re.search(self.date_pattern, text)
        if date_match:
            header_info['date'] = date_match.group(1)

        # Extract department
        dept_match = re.search(
            r'GENERAL ADMINISTRATION \([^)]+\) DEPARTMENT',
            text,
            re.IGNORECASE
        )
        if dept_match:
            header_info['department'] = dept_match.group(0)

        # Extract subject
        abstract_match = re.search(
            r'ABSTRACT\s+(.+?)(?=GENERAL ADMINISTRATION|G\.O\.Ms\.No)',
            text,
            re.DOTALL | re.IGNORECASE
        )
        if abstract_match:
            subject = abstract_match.group(1).strip()
            subject = re.sub(r'\s+', ' ', subject)
            header_info['subject'] = subject

        # Extract effective date
        effective_patterns = [
            r'deemed to have come into force.*?from[:\s]+(?:the\s+)?(\d{1,2}(?:st|nd|rd|th)?\s+\w+,?\s+\d{4})',
            r'come into force.*?(?:on and from|from)\s+(\d{1,2}[-./]\d{1,2}[-./]\d{4})',
        ]
        for pattern in effective_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                header_info['effective_date'] = match.group(1)
                break

        return header_info

    def parse_go_header(self, text: str) -> Dict[str, str]:
        """Extract GO header using Gemini"""
        if self.gemini:
            gemini_result = self.gemini.extract_go_metadata(text)
            if gemini_result:
                return gemini_result

        # No fallback
        print("  ✗ Gemini extraction failed or disabled. No fallback used.")
        return {
            'goms_no': '',
            'abstract': '',
            'notification': '',
            'signed_by': '',
            'signed_to': ''
        }

    def parse_references(self, text: str) -> List[str]:
        """Extract references from 'Read the following' section"""
        references = []

        ref_match = re.search(
            r'Read the following[:\s-]+(.+?)(?=ORDER:|NOTIFICATION|\*\*\*)',
            text,
            re.DOTALL | re.IGNORECASE
        )

        if ref_match:
            ref_text = ref_match.group(1)
            # Split by numbered items
            ref_items = re.findall(r'\d+\.?\s+(.+?)(?=\d+\.|\Z)', ref_text, re.DOTALL)
            references = [ref.strip() for ref in ref_items if ref.strip()]

        return references

    def _split_amendment_blocks(self, text: str) -> List[str]:
        """Split the amendments section into individual amendment blocks"""
        # Pattern 1: Numbered amendments like (1), (2), etc.
        numbered_splits = re.split(r'(?=\(\d+\)\s+In\s+)', text)

        if len(numbered_splits) > 1:
            return [s.strip() for s in numbered_splits if s.strip()]

        # Pattern 2: Split by "In rule-X" or "For clause"
        rule_splits = re.split(r'(?=(?:In\s+rule|For\s+clause|In\s+sub-rule))', text, flags=re.IGNORECASE)

        if len(rule_splits) > 1:
            return [s.strip() for s in rule_splits if s.strip()]

        # If no clear splits, return as single block
        return [text.strip()] if text.strip() else []

    def parse_single_amendment(self, text: str) -> Optional[Amendment]:
        """Parse a single amendment using Gemini"""
        if not text:
            return None

        if self.gemini:
            gemini_result = self.gemini.extract_amendment_details(text)
            if gemini_result:
                # Handle case where Gemini returns a list instead of dict
                if isinstance(gemini_result, list):
                    if len(gemini_result) > 0:
                        gemini_result = gemini_result[0]
                    else:
                        gemini_result = None

                if isinstance(gemini_result, dict):
                    return Amendment(
                        rule_no=gemini_result.get('rule_no', 'Unknown'),
                        sub_rule=gemini_result.get('sub_rule'),
                        clause=gemini_result.get('clause'),
                        sub_clause=gemini_result.get('sub_clause'),
                        proviso_no=gemini_result.get('proviso_no'),
                        additional_position_ctx=gemini_result.get('additional_position_ctx'),
                        type_of_action=gemini_result.get('type_of_action', 'sub'),
                        target_text=gemini_result.get('target_text'),
                        updated_text=gemini_result.get('updated_text'),
                        raw_amendment_text=text,
                        confidence=gemini_result.get('confidence', 'high')
                    )

        # No fallback
        print("  ✗ Gemini extraction failed or disabled. No fallback used.")
        return None

    def parse_amendments(self, text: str) -> List[Amendment]:
        """Parse the AMENDMENTS section"""
        amendments = []

        # Find the AMENDMENTS section
        amendment_section_match = re.search(
            r'AMENDMENTS?\s+(.+?)(?=\(BY ORDER AND IN THE NAME|\Z)',
            text,
            re.DOTALL | re.IGNORECASE
        )

        if not amendment_section_match:
            return amendments

        amendment_text = amendment_section_match.group(1)

        # Split into individual amendments
        amendment_blocks = self._split_amendment_blocks(amendment_text)

        # Parse each amendment
        for i, block in enumerate(amendment_blocks, 1):
            print(f"    Parsing amendment {i}/{len(amendment_blocks)}...", end='')
            amendment = self.parse_single_amendment(block)
            if amendment:
                amendments.append(amendment)
                conf_emoji = "🟢" if amendment.confidence == "high" else "🟡" if amendment.confidence == "medium" else "🔴"
                print(f" {conf_emoji} {amendment.confidence}")
            else:
                print(" ✗")

        return amendments

    def parse_go(self, go_text: str) -> GoDocument:
        """Parse a complete GO document"""
        print("  Extracting metadata...", end='')
        header_info = self.parse_go_header(go_text)
        print(" ✓")

        print("  Extracting references...", end='')
        references = self.parse_references(go_text)
        print(f" ✓ ({len(references)} found)")

        print("  Parsing amendments...")
        amendments = self.parse_amendments(go_text)

        go_doc = GoDocument(
            goms_no=header_info.get('goms_no', ''),
            abstract=header_info.get('abstract', ''),
            references=references,
            notification=header_info.get('notification', ''),
            amendment=amendments,
            signed_by=header_info.get('signed_by', ''),
            signed_to=header_info.get('signed_to', ''),
            raw_text=go_text
        )

        return go_doc

    def parse_pdf_file(self, pdf_path: str) -> List[GoDocument]:
        """Parse a PDF file containing one or more GOs"""
        print(f"\n{'='*60}")
        print(f"Processing: {pdf_path}")
        print('='*60)

        print("Extracting text from PDF...", end='')
        text = self.extract_text_from_pdf(pdf_path)
        print(" ✓")

        print("Splitting into individual GOs...", end='')
        go_texts = self.split_into_gos(text)
        print(f" ✓ ({len(go_texts)} found)")

        go_documents = []
        for i, go_text in enumerate(go_texts, 1):
            print(f"\nParsing GO {i}/{len(go_texts)}:")
            try:
                go_doc = self.parse_go(go_text)
                go_documents.append(go_doc)

                if go_doc.goms_no:
                    high_conf = sum(1 for a in go_doc.amendment if a.confidence == "high")
                    print(f"  ✓ {go_doc.goms_no} - {len(go_doc.amendment)} amendment(s) [{high_conf} high confidence]")
                else:
                    print(f"  ⚠ Empty document (likely page number)")
            except Exception as e:
                print(f"  ✗ Error: {e}")
                import traceback
                traceback.print_exc()

        return go_documents

    def export_to_json(self, go_documents: List[GoDocument], output_path: str):
        """Export to JSON"""
        from dataclasses import asdict
        data = [asdict(doc) for doc in go_documents]

        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

        print(f"\n✓ Exported to {output_path}")

    def export_to_markdown(self, go_documents: List[GoDocument], output_path: str):
        """Export to Markdown"""
        from dataclasses import asdict
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write("# Government Order Amendments (Enhanced Extraction)\n\n")
            f.write(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
            f.write(f"Total GOs: {len(go_documents)}\n\n")

            if any(doc.amendment and doc.amendment[0].confidence for doc in go_documents):
                f.write("**Extraction Method:** Vertex AI Gemini API\n\n")
            else:
                f.write("**Extraction Method:** Regex (Fallback)\n\n")

            f.write("---\n\n")

            for doc in go_documents:
                if not doc.goms_no:
                    continue

                f.write(f"## {doc.goms_no}\n\n")
                f.write(f"**Abstract:** {doc.abstract}\n\n")

                if doc.references:
                    f.write("**References:**\n")
                    for ref in doc.references:
                        f.write(f"- {ref}\n")
                    f.write("\n")

                if doc.notification:
                    f.write(f"**Notification:**\n{doc.notification}\n\n")

                f.write(f"### Amendments ({len(doc.amendment)})\n\n")

                for i, amendment in enumerate(doc.amendment, 1):
                    conf_emoji = "🟢" if amendment.confidence == "high" else "🟡" if amendment.confidence == "medium" else "🔴"
                    f.write(f"#### Amendment {i} {conf_emoji}\n\n")
                    f.write(f"- **Rule:** {amendment.rule_no}\n")

                    if amendment.sub_rule:
                        f.write(f"- **Sub-rule:** {amendment.sub_rule}\n")
                    if amendment.clause:
                        f.write(f"- **Clause:** {amendment.clause}\n")
                    if amendment.sub_clause:
                        f.write(f"- **Sub-clause:** {amendment.sub_clause}\n")
                    if amendment.proviso_no:
                        f.write(f"- **Proviso:** {amendment.proviso_no}\n")
                    if amendment.additional_position_ctx:
                        f.write(f"- **Position Context:** {amendment.additional_position_ctx}\n")

                    f.write(f"- **Action:** {amendment.type_of_action}\n")
                    f.write(f"- **Confidence:** {amendment.confidence}\n")

                    if amendment.target_text:
                        f.write(f"- **Target Text:** \"{amendment.target_text}\"\n")

                    if amendment.updated_text:
                        f.write(f"- **Updated Text:** \"{amendment.updated_text}\"\n")

                    f.write("\n")

                if doc.signed_by:
                    f.write(f"**Signed By:** {doc.signed_by}\n\n")

                if doc.signed_to:
                    f.write(f"**Signed To:** {doc.signed_to}\n\n")

                f.write("---\n\n")

        print(f"✓ Exported to {output_path}")