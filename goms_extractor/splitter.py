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
from dotenv import load_dotenv


def analyze_page_regex(text: str) -> Dict[str, Any]:
    """
    Analyzes a page using regex to identify GO Start/End.
    STRICT MODE: Splits only by Heading ("GOVERNMENT OF...")
    """
    is_start = False
    is_end = False
    goms_no = None
    
    # Start detection - STRICTLY BY HEADING
    # Look for "GOVERNMENT OF" in the first 300 characters (Header)
    # This is the primary signal for a new GO.
    if "GOVERNMENT OF" in text[:300].upper():
        is_start = True
        
        # Extract GOMs No for metadata if available
        match = re.search(r'G\.O\.Ms\.No\.?\s*(\d+)', text, re.IGNORECASE)
        if match:
            goms_no = match.group(1)
            
    # Disable explicit end detection to rely solely on the next header (start)
    # This ensures we split "Start to Start"
    is_end = False
        
    return {
        "is_start": is_start,
        "is_end": is_end,
        "goms_no": goms_no
    }


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

        # Pre-process with OCRmyPDF
        import shutil
        import subprocess
        
        if shutil.which("ocrmypdf"):
            print(f"DEBUG: Running OCRmyPDF on input file: {input_pdf_path}...")
            temp_ocr_filename = f"ocr_{os.path.basename(input_pdf_path)}"
            temp_ocr_path = os.path.join(output_dir, temp_ocr_filename)
            
            try:
                # --skip-text: skip OCR if text is already present
                # --jobs 4: use 4 cores
                # --output-type pdf: ensure output is PDF
                subprocess.run(
                    ["ocrmypdf", "--skip-text", "--jobs", "4", input_pdf_path, temp_ocr_path],
                    check=True,
                    capture_output=True
                )
                print(f"DEBUG: OCR completed. Using OCR'd file: {temp_ocr_path}")
                input_pdf_path = temp_ocr_path # Switch to using the OCR'd file
            except subprocess.CalledProcessError as e:
                print(f"WARNING: OCRmyPDF failed: {e.stderr.decode()}. Using original PDF.")
            except Exception as e:
                print(f"WARNING: OCRmyPDF failed: {e}. Using original PDF.")
        else:
             print("WARNING: ocrmypdf not found. Skipping OCR pre-processing.")

        # Load PDF
        reader = PdfReader(input_pdf_path)
        num_pages = len(reader.pages)
        print(f"DEBUG: Loaded PDF with {num_pages} pages")

        # Extract text for all pages
        all_pages_text = []
        print(f"DEBUG: Extracting text from all pages...")
        with pdfplumber.open(input_pdf_path) as pdf:
            for i, page in enumerate(pdf.pages):
                text = page.extract_text() or ""
                all_pages_text.append((i, text))
                # print(f"  Page {i+1}: {len(text)} characters")

        # Analyze pages using regex
        results = []
        print(f"DEBUG: Analyzing {num_pages} pages using regex...")

        for i, text in all_pages_text:
            analysis = analyze_page_regex(text)
            analysis["page"] = i
            results.append(analysis)

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
                    current_go["end_page"] = page_num - 1 # Close at previous page
                    print(f"  Completed previous GO: {current_go['goms_no']} (pages {current_go['start_page']+1} to {current_go['end_page']+1})")
                    go_index.append(current_go)

                current_go = {
                    "goms_no": goms_no or "Unknown",
                    "start_page": page_num, # 0-indexed
                    "end_page": None # Will be set later
                }
                print(f"  Started new GO: {current_go['goms_no']} at page {current_go['start_page']+1}")

            # End of GO
            if is_end and current_go:
                # If we find an end marker, it's likely the end of the current GO
                # But sometimes end marker is on the same page as start (single page GO)
                # Or multiple end markers (e.g. one for notification, one for order)
                # We'll assume the last end marker closes it, or the next start marker closes it.
                # For now, let's just mark it. If we encounter a new start, we'll close it anyway.
                # If we encounter an end, we can close it, but what if there are pages after?
                # Usually "SECTION OFFICER" is the very end.
                current_go["end_page"] = page_num
                # We don't append yet, in case there are multiple end markers or we want to wait for next start?
                # Actually, if we close it here, and there's no next start immediately, we might miss pages?
                # But "SECTION OFFICER" is usually the end.
                # Let's close it.
                print(f"  Ended GO: {current_go['goms_no']} at page {current_go['end_page']+1}")
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
        
        # Print token usage summary
        from .token_tracker import TokenTracker
        TokenTracker().print_summary()
        
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