
"""
Enhanced GO Amendment Parser with Vertex AI Gemini API
Uses LLM to improve extraction accuracy, especially for old_text and new_text
"""

import re
import json
import os
from typing import List, Dict, Optional
from dataclasses import dataclass, asdict
from datetime import datetime
import pdfplumber
from google.cloud import aiplatform
from vertexai.generative_models import GenerativeModel, GenerationConfig
import vertexai


@dataclass
class Amendment:
    """Represents a single amendment within a GO"""
    rule_reference: str
    amendment_type: str
    location: str
    old_text: Optional[str]
    new_text: Optional[str]
    full_description: str
    confidence: str = "medium"  # low, medium, high


@dataclass
class GoDocument:
    """Represents a complete GO document"""
    go_number: str
    date: str
    subject: str
    department: str
    references: List[str]
    effective_date: Optional[str]
    amendments: List[Amendment]
    raw_text: str


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
            self.project_id = project_id or os.environ.get("GOOGLE_CLOUD_PROJECT")
            self.location = location
            
            if not self.project_id:
                print("WARNING: GOOGLE_CLOUD_PROJECT not set. Gemini extraction disabled.")
                self.enabled = False
                return
            
            # Initialize Vertex AI
            vertexai.init(project=self.project_id, location=self.location)
            
            # Initialize Gemini model
            self.model = GenerativeModel("gemini-1.5-flash-002")
            
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
1. The exact rule being amended (e.g., "Rule 12", "Rule 22(3)(a)")
2. The type of amendment (substitution, insertion, deletion, modification)
3. The specific location within the rule (e.g., "sub-rule (1)", "clause (a)", "Explanation (iii)")
4. For SUBSTITUTIONS: Extract BOTH the old text being replaced AND the new text
5. For INSERTIONS: Extract the new text being added
6. For DELETIONS: Extract the text being removed

AMENDMENT TEXT:
{amendment_text}

CRITICAL INSTRUCTIONS:
- For substitutions, look for patterns like "for the words X, the words Y shall be substituted"
- The OLD_TEXT is typically after "for the words" or "for clause"
- The NEW_TEXT is typically after "the following shall be substituted" or "the words X shall be substituted"
- Extract complete sentences/phrases, not fragments
- If text is in quotes, include the quotes
- If you cannot find old_text or new_text, set it to null

OUTPUT FORMAT:
Respond with ONLY a valid JSON object (no markdown, no explanations):
{{
  "rule_reference": "Rule X or Rule X(Y)(Z)",
  "amendment_type": "substitution|insertion|deletion|modification",
  "location": "specific location within rule",
  "old_text": "exact text being replaced (for substitutions only, otherwise null)",
  "new_text": "exact text being added/substituted (null if deletion)",
  "confidence": "high|medium|low"
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
        
        prompt = f"""Extract metadata from this Government Order document.

DOCUMENT TEXT:
{text[:2000]}

Extract the following information:
1. GO Number (e.g., "G.O.Ms.No.464")
2. Date (in DD-MM-YYYY format)
3. Department name
4. Subject/Abstract
5. Effective date (when the amendment comes into force)

RESPOND WITH ONLY A JSON OBJECT:
{{
  "go_number": "G.O.Ms.No.XXX",
  "date": "DD-MM-YYYY",
  "department": "Department name",
  "subject": "Brief subject",
  "effective_date": "DD-MM-YYYY or descriptive date (null if not found)"
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
        """Extract text from PDF file"""
        text = ""
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages:
                page_text = page.extract_text()
                if page_text:
                    text += page_text + "\n"
        return text
    
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
        """Extract GO header using Gemini or regex fallback"""
        # Try Gemini first
        if self.gemini:
            gemini_result = self.gemini.extract_go_metadata(text)
            if gemini_result:
                return gemini_result
        
        # Fallback to regex
        return self.parse_go_header_regex(text)
    
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
    
    def _parse_amendment_regex(self, text: str) -> Optional[Amendment]:
        """Parse amendment using regex (fallback method)"""
        if not text:
            return None
        
        # Extract rule reference
        rule_match = re.search(
            r'(?:In\s+|For\s+)?(?:rule|clause|sub-rule)[-\s]*(\d+[A-Z]?(?:\([^)]+\))*(?:\s*\([^)]+\))*)',
            text,
            re.IGNORECASE
        )
        rule_reference = rule_match.group(1) if rule_match else "Unknown"
        
        # Extract location
        location_match = re.search(
            r'in\s+(sub-rule\s*\([^)]+\)|clause\s*\([^)]+\)|Explanation\s*\([^)]+\))',
            text,
            re.IGNORECASE
        )
        location = location_match.group(1) if location_match else ""
        
        # Determine amendment type
        text_lower = text.lower()
        if 'substituted' in text_lower or 'substitute' in text_lower:
            amendment_type = 'substitution'
        elif 'inserted' in text_lower or 'insert' in text_lower or 'added' in text_lower:
            amendment_type = 'insertion'
        elif 'omitted' in text_lower or 'deleted' in text_lower:
            amendment_type = 'deletion'
        else:
            amendment_type = 'modification'
        
        # Extract old text (for substitution)
        old_text = None
        if amendment_type == 'substitution':
            # Pattern: for the words "X" or for clause (X)
            old_patterns = [
                r'[Ff]or\s+(?:the\s+)?(?:words?\s+)?["\']([^"\']+)["\']',
                r'[Ff]or\s+(?:the\s+)?(?:clause|Explanation)\s*\(([^)]+)\)',
            ]
            for pattern in old_patterns:
                old_match = re.search(pattern, text)
                if old_match:
                    old_text = old_match.group(1).strip()
                    break
        
        # Extract new text
        new_text = None
        new_patterns = [
            r'the\s+following\s+shall\s+be\s+(?:substituted|inserted|added)[,:\s-]+namely[:\s-]*["\']?(.+?)["\']?\s*(?:\(BY\s+ORDER|\Z)',
            r'the\s+words?\s+["\']([^"\']+)["\']?\s+shall\s+be\s+(?:substituted|inserted)',
        ]
        
        for pattern in new_patterns:
            new_match = re.search(pattern, text, re.DOTALL | re.IGNORECASE)
            if new_match:
                new_text = new_match.group(1).strip()
                # Clean up and limit length
                new_text = re.sub(r'\s+', ' ', new_text)
                if len(new_text) > 500:
                    new_text = new_text[:500] + "..."
                break
        
        return Amendment(
            rule_reference=rule_reference,
            amendment_type=amendment_type,
            location=location,
            old_text=old_text,
            new_text=new_text,
            full_description=text[:1000],
            confidence="low"
        )
    
    def parse_single_amendment(self, text: str) -> Optional[Amendment]:
        """Parse a single amendment using Gemini or regex fallback"""
        if not text:
            return None
        
        # Try Gemini first
        if self.gemini:
            gemini_result = self.gemini.extract_amendment_details(text)
            if gemini_result:
                return Amendment(
                    rule_reference=gemini_result.get('rule_reference', 'Unknown'),
                    amendment_type=gemini_result.get('amendment_type', 'modification'),
                    location=gemini_result.get('location', ''),
                    old_text=gemini_result.get('old_text'),
                    new_text=gemini_result.get('new_text'),
                    full_description=text[:1000],
                    confidence=gemini_result.get('confidence', 'high')
                )
        
        # Fallback to regex
        return self._parse_amendment_regex(text)
    
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
            go_number=header_info.get('go_number', ''),
            date=header_info.get('date', ''),
            subject=header_info.get('subject', ''),
            department=header_info.get('department', ''),
            references=references,
            effective_date=header_info.get('effective_date'),
            amendments=amendments,
            raw_text=go_text[:2000] if len(go_text) > 2000 else go_text
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
                
                if go_doc.go_number:
                    high_conf = sum(1 for a in go_doc.amendments if a.confidence == "high")
                    print(f"  ✓ {go_doc.go_number} - {len(go_doc.amendments)} amendment(s) [{high_conf} high confidence]")
                else:
                    print(f"  ⚠ Empty document (likely page number)")
            except Exception as e:
                print(f"  ✗ Error: {e}")
                import traceback
                traceback.print_exc()
        
        return go_documents
    
    def export_to_json(self, go_documents: List[GoDocument], output_path: str):
        """Export to JSON"""
        data = [asdict(doc) for doc in go_documents]
        
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        
        print(f"\n✓ Exported to {output_path}")
    
    def export_to_markdown(self, go_documents: List[GoDocument], output_path: str):
        """Export to Markdown"""
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write("# Government Order Amendments (Enhanced Extraction)\n\n")
            f.write(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
            f.write(f"Total GOs: {len(go_documents)}\n\n")
            
            if any(doc.amendments and doc.amendments[0].confidence for doc in go_documents):
                f.write("**Extraction Method:** Vertex AI Gemini API\n\n")
            else:
                f.write("**Extraction Method:** Regex (Fallback)\n\n")
            
            f.write("---\n\n")
            
            for doc in go_documents:
                if not doc.go_number:
                    continue
                
                f.write(f"## {doc.go_number}\n\n")
                f.write(f"**Date:** {doc.date}\n\n")
                f.write(f"**Department:** {doc.department}\n\n")
                f.write(f"**Subject:** {doc.subject}\n\n")
                
                if doc.effective_date:
                    f.write(f"**Effective Date:** {doc.effective_date}\n\n")
                
                if doc.references:
                    f.write("**References:**\n")
                    for ref in doc.references:
                        f.write(f"- {ref}\n")
                    f.write("\n")
                
                f.write(f"### Amendments ({len(doc.amendments)})\n\n")
                
                for i, amendment in enumerate(doc.amendments, 1):
                    conf_emoji = "🟢" if amendment.confidence == "high" else "🟡" if amendment.confidence == "medium" else "🔴"
                    f.write(f"#### Amendment {i} {conf_emoji}\n\n")
                    f.write(f"- **Rule:** {amendment.rule_reference}\n")
                    f.write(f"- **Type:** {amendment.amendment_type}\n")
                    f.write(f"- **Confidence:** {amendment.confidence}\n")
                    
                    if amendment.location:
                        f.write(f"- **Location:** {amendment.location}\n")
                    
                    if amendment.old_text:
                        f.write(f"- **Old Text:** \"{amendment.old_text}\"\n")
                    
                    if amendment.new_text:
                        f.write(f"- **New Text:** \"{amendment.new_text}\"\n")
                    
                    f.write("\n")
                
                f.write("---\n\n")
        
        print(f"✓ Exported to {output_path}")


def main():
    """Main function"""
    import sys
    
    if len(sys.argv) < 2:
        print("Enhanced GO Amendment Parser with Vertex AI Gemini")
        print("\nUsage: python go_parser_gemini.py <pdf_file1> [pdf_file2] ...")
        print("\nEnvironment Variables:")
        print("  GOOGLE_CLOUD_PROJECT - Your GCP project ID")
        print("  GOOGLE_APPLICATION_CREDENTIALS - Path to service account key JSON")
        print("\nExamples:")
        print("  # With Gemini API (recommended)")
        print("  export GOOGLE_CLOUD_PROJECT='your-project-id'")
        print("  export GOOGLE_APPLICATION_CREDENTIALS='path/to/key.json'")
        print("  python go_parser_gemini.py GO_464.pdf")
        print("\n  # Without Gemini (regex only)")
        print("  python go_parser_gemini.py --no-gemini GO_464.pdf")
        sys.exit(1)
    
    # Check for --no-gemini flag
    use_gemini = True
    args = sys.argv[1:]
    
    if '--no-gemini' in args:
        use_gemini = False
        args.remove('--no-gemini')
        print("Running in regex-only mode (Gemini disabled)")
    
    # Initialize parser
    parser = EnhancedGoAmendmentParser(use_gemini=use_gemini)
    all_documents = []
    
    # Parse each PDF file
    for pdf_path in args:
        try:
            documents = parser.parse_pdf_file(pdf_path)
            all_documents.extend(documents)
        except Exception as e:
            print(f"\n✗ Error processing {pdf_path}: {e}")
            import traceback
            traceback.print_exc()
    
    # Export results
    if all_documents:
        print(f"\n{'='*60}")
        print("Exporting Results")
        print('='*60)
        
        valid_docs = [doc for doc in all_documents if doc.go_number]
        
        parser.export_to_json(all_documents, "../outputs/go_amendments_enhanced.json")
        parser.export_to_markdown(all_documents, "../outputs/go_amendments_enhanced.md")
        
        # Print statistics
        print(f"\n{'='*60}")
        print("Extraction Statistics")
        print('='*60)
        print(f"Total documents: {len(all_documents)}")
        print(f"Valid GOs: {len(valid_docs)}")
        
        total_amendments = sum(len(doc.amendments) for doc in valid_docs)
        print(f"Total amendments: {total_amendments}")
        
        if parser.gemini and parser.gemini.enabled:
            high_conf = sum(1 for doc in valid_docs for a in doc.amendments if a.confidence == "high")
            med_conf = sum(1 for doc in valid_docs for a in doc.amendments if a.confidence == "medium")
            low_conf = sum(1 for doc in valid_docs for a in doc.amendments if a.confidence == "low")
            
            print(f"\nConfidence Distribution:")
            print(f"  🟢 High:   {high_conf} ({high_conf/total_amendments*100:.1f}%)")
            print(f"  🟡 Medium: {med_conf} ({med_conf/total_amendments*100:.1f}%)")
            print(f"  🔴 Low:    {low_conf} ({low_conf/total_amendments*100:.1f}%)")
        
        # Count successful extractions
        with_old_text = sum(1 for doc in valid_docs for a in doc.amendments if a.old_text and a.amendment_type == 'substitution')
        with_new_text = sum(1 for doc in valid_docs for a in doc.amendments if a.new_text)
        
        print(f"\nExtraction Success:")
        print(f"  Old text extracted: {with_old_text} amendments")
        print(f"  New text extracted: {with_new_text} amendments")
        
        print(f"\n✓ Successfully processed {len(valid_docs)} GO document(s)")
    else:
        print("\n✗ No documents were successfully parsed")


if __name__ == "__main__":
    main()