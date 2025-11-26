"""
GO splitter module for splitting PDFs containing multiple Government Orders (GOs) into individual PDF files.
"""

import os
import re
import json
import time
import math
from typing import List, Dict, Any, Optional

import pdfplumber
from pypdf import PdfReader, PdfWriter
from dotenv import load_dotenv
import vertexai
from vertexai.generative_models import GenerativeModel, GenerationConfig


def analyze_page_batch(pages_data: list, model: GenerativeModel) -> list:
    """
    Analyzes a batch of pages using Gemini to identify GO Start/End.

    Args:
        pages_data: List of tuples (page_num, text)
        model: Initialized Gemini model

    Returns:
        List of dicts with classification results
    """
    print(f"DEBUG: Analyzing batch of {len(pages_data)} pages with Gemini...")

    prompt_text = ""
    for page_num, text in pages_data:
        # Limit text per page to avoid context limits, header/footer usually enough
        clean_text = text[:1500].replace("\n", " ") if text else "NO TEXT"
        prompt_text += f"--- PAGE {page_num + 1} ---\n{clean_text}\n\n"

    prompt = f"""Analyze the following pages from a Government Order (GO) document bundle.
For EACH page, determine:
1. Is it the START of a new GO? (Look for "G.O.Ms.No", "GOVERNMENT OF...", "ABSTRACT")
2. Is it the END of a GO? (Look for "BY ORDER AND IN THE NAME OF THE GOVERNOR", "SECTION OFFICER", "SECRETARY TO GOVERNMENT")
3. If it's a START, extract the GOMs Number.

PAGES:
{prompt_text}

Respond with a JSON LIST of objects, one for each page:
[
  {{
    "page": <page_number>,
    "is_start": true/false,
    "is_end": true/false,
    "goms_no": "number or null"
  }},
  ...
]
"""

    try:
        print(f"DEBUG: Sending batch analysis request to Gemini...")
        response = model.generate_content(
            prompt,
            generation_config=GenerationConfig(
                response_mime_type="application/json",
                temperature=0.1
            )
        )
        print(f"DEBUG: Gemini response received, parsing JSON...")
        result = json.loads(response.text)
        print(f"DEBUG: Batch analysis completed successfully, found {len([r for r in result if r['is_start'] or r['is_end']])} GO boundaries in batch")
        return result
    except Exception as e:
        print(f"⚠️ Batch analysis failed: {e}")
        # Return empty results for this batch to avoid crashing
        result = [{"page": p[0] + 1, "is_start": False, "is_end": False, "goms_no": None} for p in pages_data]
        print(f"DEBUG: Returned empty results for batch due to error")
        return result


def split_goms(input_pdf_path: str, output_dir: str = None) -> Dict[str, Any]:
    """
    Split a PDF containing multiple Government Orders (GOs) into individual PDF files.

    Args:
        input_pdf_path: Path to the input PDF file containing multiple GOs
        output_dir: Directory to save the split PDFs (default: outputs/split_goms)

    Returns:
        Dictionary containing information about the split process:
        {
            "status": "success|error",
            "message": "Description of what happened",
            "split_files": List of paths to created files,
            "go_index": List of GO information with start/end pages
        }
    """
    print(f"DEBUG: Starting to split PDF: {input_pdf_path}")
    try:
        # Set default output directory
        if output_dir is None:
            script_dir = os.path.dirname(os.path.abspath(__file__))
            project_root = os.path.dirname(script_dir)
            output_dir = os.path.join(project_root, "outputs", "split_goms")

        os.makedirs(output_dir, exist_ok=True)
        print(f"DEBUG: Output directory created/verified: {output_dir}")

        # Load environment variables
        script_dir = os.path.dirname(os.path.abspath(__file__))
        project_root = os.path.dirname(script_dir)
        env_path = os.path.join(project_root, ".env")
        load_dotenv(env_path)

        # Initialize Gemini
        project_id = os.environ.get("GOOGLE_CLOUD_PROJECT")
        if not project_id:
            print(f"ERROR: GOOGLE_CLOUD_PROJECT environment variable not set")
            return {
                "status": "error",
                "message": "GOOGLE_CLOUD_PROJECT environment variable not set",
                "split_files": [],
                "go_index": []
            }

        print(f"DEBUG: Initializing Vertex AI with project: {project_id}")
        vertexai.init(project=project_id, location="asia-south1")
        model = GenerativeModel("gemini-2.5-flash")
        print(f"DEBUG: Gemini model initialized")

        # Load PDF
        reader = PdfReader(input_pdf_path)
        num_pages = len(reader.pages)
        print(f"DEBUG: Loaded PDF with {num_pages} pages")

        # Extract text for all pages first (faster than doing it in loop)
        all_pages_text = []
        print(f"DEBUG: Extracting text from all pages...")
        with pdfplumber.open(input_pdf_path) as pdf:
            for i, page in enumerate(pdf.pages):
                text = page.extract_text() or ""
                all_pages_text.append((i, text))
                print(f"  Page {i+1}: {len(text)} characters")

        # Process in batches
        BATCH_SIZE = 10
        results = []
        print(f"DEBUG: Processing {num_pages} pages in batches of {BATCH_SIZE}...")

        for i in range(0, num_pages, BATCH_SIZE):
            batch = all_pages_text[i : i + BATCH_SIZE]
            print(f"  Processing batch {i//BATCH_SIZE + 1}: pages {batch[0][0]+1}-{batch[-1][0]+1}")
            batch_results = analyze_page_batch(batch, model)
            results.extend(batch_results)
            print(f"  Batch results: {len([r for r in batch_results if r['is_start'] or r['is_end']])} GO boundaries detected")
            time.sleep(10) # Rate limiting for quota

        print(f"DEBUG: Analyzed all pages, found {len([r for r in results if r['is_start'] or r['is_end']])} potential GO boundaries")

        # Build Index
        go_index = []
        current_go = None
        print(f"DEBUG: Building GO index from analysis results...")

        for res in results:
            page_num = res.get("page")
            is_start = res.get("is_start")
            is_end = res.get("is_end")
            goms_no = res.get("goms_no")

            # Start of new GO
            if is_start:
                # If previous GO was open, close it at previous page
                if current_go:
                    current_go["end_page"] = page_num - 2 # 0-indexed, previous page
                    print(f"  Completed previous GO: {current_go['goms_no']} (pages {current_go['start_page']+1} to {current_go['end_page']+1})")
                    go_index.append(current_go)

                current_go = {
                    "goms_no": goms_no or "Unknown",
                    "start_page": page_num - 1, # 0-indexed
                    "end_page": None # Will be set later
                }
                print(f"  Started new GO: {current_go['goms_no']} at page {current_go['start_page']+1}")

            # End of GO
            if is_end and current_go:
                current_go["end_page"] = page_num - 1 # 0-indexed
                print(f"  Ended GO: {current_go['goms_no']} at page {current_go['end_page']+1} (pages {current_go['start_page']+1} to {current_go['end_page']+1})")
                go_index.append(current_go)
                current_go = None

        # Handle last GO if still open
        if current_go:
            current_go["end_page"] = num_pages - 1
            print(f"  Completed final GO: {current_go['goms_no']} (pages {current_go['start_page']+1} to {current_go['end_page']+1})")
            go_index.append(current_go)

        print(f"DEBUG: GO index built with {len(go_index)} documents")

        # Split Files
        split_files = []
        print(f"DEBUG: Creating individual PDF files...")
        for i, go in enumerate(go_index):
            start = go["start_page"]
            end = go["end_page"]
            num = go["goms_no"]

            print(f"  Creating file {i+1}/{len(go_index)}: GO {num}, pages {start+1} to {end+1}")

            # Validate range
            if start > end:
                print(f"   ⚠️ Invalid range for GO {num}: {start+1}-{end+1}. Skipping.")
                continue

            writer = PdfWriter()
            for p in range(start, end + 1):
                writer.add_page(reader.pages[p])

            # Sanitize GO number for filename
            clean_num = re.sub(r'[^\w\d-]', '', num.replace("G.O.Ms.No.", "").strip())
            filename = f"GO_{clean_num}_Pages_{start+1}-{end+1}.pdf"
            filename = re.sub(r'[<>:"/\\|?*]', '_', filename)
            output_path = os.path.join(output_dir, filename)

            with open(output_path, "wb") as f:
                writer.write(f)

            split_files.append(output_path)
            print(f"    Created: {output_path}")

        print(f"DEBUG: Splitting completed successfully")
        result = {
            "status": "success",
            "message": f"Successfully split {input_pdf_path} into {len(split_files)} files. Output directory: {output_dir}",
            "split_files": split_files,
            "go_index": go_index
        }
        print(f"DEBUG: Returning result - {len(split_files)} files created")
        return result
    except Exception as e:
        print(f"ERROR: Error splitting GOs: {str(e)}")
        import traceback
        traceback.print_exc()
        return {
            "status": "error",
            "message": f"Error splitting GOs: {str(e)}",
            "split_files": [],
            "go_index": []
        }