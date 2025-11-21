"""
Rule Mapper - Extract Multiple Amendments from Government Orders
Clean implementation following SOLID and KISS principles
Uses Vertex AI API for intelligent extraction
"""

import json
import os
import re
import time
import sys
from abc import ABC, abstractmethod
from dataclasses import dataclass, asdict
from typing import List, Optional, Dict
from enum import Enum
from dotenv import load_dotenv

from google.cloud import aiplatform
import vertexai
from vertexai.generative_models import GenerativeModel


# ============================================================================
# DOMAIN MODELS
# ============================================================================

class AmendmentType(Enum):
    SUBSTITUTION = "substitution"
    OMISSION = "omission"
    ADDITION = "addition"
    UNKNOWN = "unknown"


@dataclass
class RuleReference:
    """Represents a hierarchical rule reference"""
    rule: str
    subrule: Optional[str] = None
    clause: Optional[str] = None
    subclause: Optional[str] = None

    def to_path(self) -> str:
        """Example: 22(2)(e)(i)"""
        parts = [self.rule]
        if self.subrule: parts.append(f"({self.subrule})")
        if self.clause: parts.append(f"({self.clause})")
        if self.subclause: parts.append(f"({self.subclause})")
        return ''.join(parts)


@dataclass
class Amendment:
    """Single amendment extracted from a GO"""
    go_number: str
    sequence: int
    rule_target: RuleReference
    amendment_type: AmendmentType
    old_text: Optional[str] = None
    new_text: Optional[str] = None
    raw_instruction: str = ""
    confidence: float = 0.0


# ============================================================================
# EXTRACTOR INTERFACE (SOLID: Single Responsibility)
# ============================================================================

class IAmendmentExtractor(ABC):
    """Interface for amendment extraction strategies"""

    @abstractmethod
    def extract_from_text(self, text: str) -> List[Dict]:
        """Extract amendment data from instruction text"""
        pass


# ============================================================================
# VERTEX AI EXTRACTOR (SOLID: Open/Closed Principle)
# ============================================================================

class VertexAIAmendmentExtractor(IAmendmentExtractor):
    """Uses Vertex AI Gemini to extract amendments intelligently"""

    def __init__(self, project_id: str, location: str = "us-central1"):
        """
        Initialize Vertex AI

        Args:
            project_id: GCP project ID
            location: GCP region (default: us-central1)
        """
        vertexai.init(project=project_id, location=location)
        self.model = GenerativeModel('gemini-1.5-flash')
        print(f"Initialized Vertex AI in project '{project_id}', location '{location}'")

    def extract_from_text(self, text: str) -> List[Dict]:
        """Extract multiple amendments from instruction text"""
        prompt = f"""
Extract ALL amendments from this Government Order text.
Each amendment modifies a specific rule. Return a JSON array.

TEXT:
{text[:2000]}

OUTPUT (JSON array only, no explanation):
[
  {{
    "rule": "22",
    "subrule": "2",
    "clause": "e",
    "subclause": null,
    "type": "substitution|omission|addition",
    "old": "text being replaced",
    "new": "new text",
    "confidence": 0.9
  }}
]

Return empty array [] if no amendments found.
JSON:
"""

        try:
            response = self.model.generate_content(prompt)
            result = response.text.strip()

            # Clean markdown
            if '```json' in result:
                result = result.split('```json')[1].split('```')[0]
            elif '```' in result:
                result = result.split('```')[1].split('```')[0]

            data = json.loads(result.strip())

            # Ensure it's a list
            if isinstance(data, dict):
                data = [data]

            time.sleep(1)  # Rate limiting
            return data

        except Exception as e:
            print(f"  Vertex AI extraction failed: {e}")
            return []


# ============================================================================
# REGEX FALLBACK EXTRACTOR (SOLID: Liskov Substitution)
# ============================================================================

class RegexAmendmentExtractor(IAmendmentExtractor):
    """Fallback extractor using regex patterns"""

    def __init__(self):
        self.rule_pattern = re.compile(
            r'rule[\s\-]*(\d+)(?:.*?sub[\s\-]*rule\s*\(([^\)]+)\))?'
            r'(?:.*?clause\s*\(([^\)]+)\))?(?:.*?sub[\s\-]*clause\s*\(([^\)]+)\))?',
            re.IGNORECASE | re.DOTALL
        )

    def extract_from_text(self, text: str) -> List[Dict]:
        """Extract using regex patterns"""
        amendments = []

        # Find rule references
        matches = list(self.rule_pattern.finditer(text))
        if not matches:
            return []

        for match in matches:
            # Detect type
            amend_type = "unknown"
            if 'substituted' in text.lower():
                amend_type = "substitution"
            elif 'omitted' in text.lower():
                amend_type = "omission"
            elif 'added' in text.lower() or 'inserted' in text.lower():
                amend_type = "addition"

            amendments.append({
                "rule": match.group(1),
                "subrule": match.group(2),
                "clause": match.group(3),
                "subclause": match.group(4),
                "type": amend_type,
                "old": None,
                "new": None,
                "confidence": 0.6
            })

        return amendments


# ============================================================================
# AMENDMENT MAPPER (SOLID: Dependency Inversion)
# ============================================================================

class AmendmentMapper:
    """Maps amendments from parsed GO data"""

    def __init__(self, extractor: IAmendmentExtractor):
        """Inject extraction strategy"""
        self.extractor = extractor

    def map_go(self, go_data: Dict) -> List[Amendment]:
        """Extract all amendments from a single GO"""
        go_num = go_data['metadata']['go_number']
        amendments = []

        # Process each amendment instruction in the GO
        for idx, amend_data in enumerate(go_data.get('amendments', []), 1):
            instruction = amend_data.get('instruction_raw', '')

            # Extract using strategy
            extracted = self.extractor.extract_from_text(instruction)

            # Convert to domain objects
            for item in extracted:
                try:
                    rule_ref = RuleReference(
                        rule=str(item.get('rule', '')),
                        subrule=item.get('subrule'),
                        clause=item.get('clause'),
                        subclause=item.get('subclause')
                    )

                    amendment = Amendment(
                        go_number=go_num,
                        sequence=idx,
                        rule_target=rule_ref,
                        amendment_type=AmendmentType(item.get('type', 'unknown')),
                        old_text=item.get('old'),
                        new_text=item.get('new'),
                        raw_instruction=instruction[:200],
                        confidence=float(item.get('confidence', 0.5))
                    )
                    amendments.append(amendment)

                except Exception as e:
                    print(f"  Failed to parse amendment: {e}")

        return amendments

    def map_all_gos(self, parsed_gos_file: str) -> List[Amendment]:
        """Process all GOs from JSON file"""
        with open(parsed_gos_file, 'r') as f:
            gos_data = json.load(f)

        all_amendments = []

        print(f"\nProcessing {len(gos_data)} GOs...\n")

        for go_data in gos_data:
            go_num = go_data['metadata']['go_number']
            print(f"Processing GO {go_num}...", end=' ')

            amendments = self.map_go(go_data)
            all_amendments.extend(amendments)

            print(f"Found {len(amendments)} amendment(s)")

        return all_amendments


# ============================================================================
# OUTPUT FORMATTER (SOLID: Single Responsibility)
# ============================================================================

class AmendmentOutputFormatter:
    """Formats amendments for output"""

    @staticmethod
    def to_json(amendments: List[Amendment], output_file: str):
        """Save amendments to JSON file"""
        data = []

        for amend in amendments:
            data.append({
                'go_number': amend.go_number,
                'sequence': amend.sequence,
                'rule_path': amend.rule_target.to_path(),
                'rule_details': asdict(amend.rule_target),
                'type': amend.amendment_type.value,
                'old_text': amend.old_text,
                'new_text': amend.new_text,
                'confidence': amend.confidence,
                'instruction': amend.raw_instruction
            })

        with open(output_file, 'w') as f:
            json.dump(data, f, indent=2)

        print(f"\nSaved {len(amendments)} amendments to {output_file}")

    @staticmethod
    def print_summary(amendments: List[Amendment]):
        """Print summary statistics"""
        print("\n" + "="*70)
        print("SUMMARY")
        print("="*70)
        print(f"Total amendments: {len(amendments)}")

        # Count by type
        types = {}
        for a in amendments:
            types[a.amendment_type.value] = types.get(a.amendment_type.value, 0) + 1

        print("\nBy type:")
        for t, count in sorted(types.items()):
            print(f"  {t}: {count}")

        # Count by GO
        gos = {}
        for a in amendments:
            gos[a.go_number] = gos.get(a.go_number, 0) + 1

        print(f"\nGOs with multiple amendments: {sum(1 for c in gos.values() if c > 1)}")

        # Unique rules
        rules = set(a.rule_target.to_path() for a in amendments)
        print(f"Unique rules affected: {len(rules)}")


# ============================================================================
# MAIN APPLICATION
# ============================================================================

def main():
    """Main application entry point"""
    load_dotenv()
    project_id = os.environ.get('GCP_PROJECT_ID')
    location = os.environ.get('GCP_LOCATION', 'us-central1')
    input_file = '../outputs/parsed_gos.json'
    output_file = '../outputs/amendments_mapped.json'

    # Validate configuration
    if not project_id:
        print("ERROR: Environment variable GCP_PROJECT_ID not set.")
        print("\nUsage:")
        print("  export GCP_PROJECT_ID='your-project-id'")
        print("  export GCP_LOCATION='us-central1'  # Optional, defaults to us-central1")
        print("  python rule_mapper.py")
        sys.exit(1)

    print("="*70)
    print("AMENDMENTS MAPPER - Vertex AI Edition")
    print("="*70)
    print(f"GCP Project: {project_id}")
    print(f"GCP Location: {location}")
    print(f"Input: {input_file}")
    print(f"Output: {output_file}")
    print("="*70)

    # Create extractor with Vertex AI
    print("\nUsing Vertex AI API for intelligent extraction")
    extractor = VertexAIAmendmentExtractor(project_id, location)

    # Create mapper with injected strategy
    mapper = AmendmentMapper(extractor)

    # Process all GOs
    try:
        amendments = mapper.map_all_gos(input_file)

        # Output results
        formatter = AmendmentOutputFormatter()
        formatter.to_json(amendments, output_file)
        formatter.print_summary(amendments)

        # Show examples
        print("\nSample Amendments:")
        for amend in amendments[:5]:
            print(f"\n  GO {amend.go_number} -> Rule {amend.rule_target.to_path()}")
            print(f"  Type: {amend.amendment_type.value}")
            if amend.old_text and amend.new_text:
                print(f"  Change: '{amend.old_text[:50]}...' -> '{amend.new_text[:50]}...'")

        print("\n" + "="*70)
        print("SUCCESS: Processing complete!")
        print("="*70)

    except FileNotFoundError:
        print(f"\nERROR: File not found: {input_file}")
        print("Run go_parser.py first to create parsed_gos.json")
        sys.exit(1)
    except Exception as e:
        print(f"\nERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()