"""
Function tools for agents to handle Government Order (GO) processing.

This module provides the parse_amendments function for parsing amendments from GO PDFs.
"""

import os
from typing import Dict, Any

from .parser import EnhancedGoAmendmentParser
from .models import GoDocument
from dataclasses import asdict


def parse_amendments(input_pdf_path: str, use_gemini: bool = True) -> Dict[str, Any]:
    """
    Parse amendments from a Government Order (GO) PDF file.

    Args:
        input_pdf_path: Path to the input GO PDF file
        use_gemini: Whether to use Gemini API for extraction (default: True)

    Returns:
        Dictionary containing information about the parsed amendments:
        {
            "status": "success|error",
            "message": "Description of what happened",
            "documents": List of parsed GO documents with amendments
        }
    """
    print(f"DEBUG: Starting to parse amendments from PDF: {input_pdf_path}")
    try:
        parser = EnhancedGoAmendmentParser(use_gemini=use_gemini)
        print(f"DEBUG: Parser initialized with use_gemini={use_gemini}")

        documents = parser.parse_pdf_file(input_pdf_path)
        print(f"DEBUG: Parsed {len(documents)} documents from PDF")

        # Convert documents to serializable format
        serializable_docs = []
        for i, doc in enumerate(documents):
            print(f"  Processing document {i+1}: {doc.goms_no or 'Unknown'} with {len(doc.amendment)} amendments")
            doc_dict = asdict(doc)
            # Convert amendment objects to dictionaries
            amendments = []
            for j, amendment in enumerate(doc.amendment):
                amendment_dict = asdict(amendment)
                amendments.append(amendment_dict)
                print(f"    Amendment {j+1}: {amendment.type_of_action} in {amendment.rule_no} (confidence: {amendment.confidence})")
            doc_dict['amendment'] = amendments
            serializable_docs.append(doc_dict)

        # Set output directory based on the input file's location to save results
        output_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "outputs")
        os.makedirs(output_dir, exist_ok=True)
        print(f"DEBUG: Output directory prepared: {output_dir}")

        # Generate output filenames based on input PDF name
        input_filename = os.path.splitext(os.path.basename(input_pdf_path))[0]
        json_output_path = os.path.join(output_dir, f"{input_filename}_amendments.json")
        md_output_path = os.path.join(output_dir, f"{input_filename}_amendments.md")
        print(f"DEBUG: Generated output file paths:\n  JSON: {json_output_path}\n  Markdown: {md_output_path}")

        # Export results to files
        print(f"DEBUG: Exporting results to JSON...")
        parser.export_to_json(documents, json_output_path)
        print(f"DEBUG: Exporting results to Markdown...")
        parser.export_to_markdown(documents, md_output_path)

        # Count total amendments
        total_amendments = sum(len(doc.get('amendment', [])) for doc in serializable_docs)
        print(f"DEBUG: Total parsed: {len(serializable_docs)} documents with {total_amendments} amendments")

        result = {
            "status": "success",
            "message": f"Successfully parsed {len(serializable_docs)} documents with {total_amendments} amendments. Output saved to: {json_output_path} and {md_output_path}",
            "documents": serializable_docs,
            "output_files": [json_output_path, md_output_path]
        }
        print(f"DEBUG: Parse amendments completed successfully")
        return result
    except Exception as e:
        print(f"ERROR: Error parsing amendments: {str(e)}")
        import traceback
        traceback.print_exc()
        return {
            "status": "error",
            "message": f"Error parsing amendments: {str(e)}",
            "documents": []
        }