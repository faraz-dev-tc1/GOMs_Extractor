"""
Markdown converter for Government Orders (GOs).
Converts split GO PDFs into markdown files for easier processing.
"""

import os
import re
from typing import Dict, Any, List
from dotenv import load_dotenv
import os
import re
from typing import Dict, Any, List
from dotenv import load_dotenv


def convert_go_to_markdown(pdf_path: str, output_dir: str = None) -> Dict[str, Any]:
    """
    Convert a single GO PDF file to markdown format using local OCR and text extraction.
    
    Args:
        pdf_path: Path to the GO PDF file
        output_dir: Directory to save the markdown file (default: outputs/markdown_goms)
    
    Returns:
        Dictionary containing:
        {
            "status": "success|error",
            "message": "Description of what happened",
            "markdown_path": "Path to the created markdown file",
            "goms_no": "GO number extracted from the document"
        }
    """
    print(f"DEBUG: Converting PDF to markdown (local): {pdf_path}")
    try:
        # Set default output directory
        if output_dir is None:
            script_dir = os.path.dirname(os.path.abspath(__file__))
            project_root = os.path.dirname(script_dir)
            output_dir = os.path.join(project_root, "outputs", "markdown_goms")
        
        os.makedirs(output_dir, exist_ok=True)
        print(f"DEBUG: Output directory created/verified: {output_dir}")
        
        # Ensure OCRmyPDF is available
        import subprocess
        import shutil
        
        if not shutil.which("ocrmypdf"):
             print("WARNING: ocrmypdf not found. Skipping OCR step and relying on existing text.")
        else:
            # Run OCRmyPDF to ensure text is available (skip if already has text)
            # We'll output to a temp file
            temp_pdf_path = os.path.join(output_dir, f"temp_{os.path.basename(pdf_path)}")
            print(f"DEBUG: Running OCRmyPDF on {pdf_path}...")
            try:
                # --skip-text: skip OCR if text is already present
                # --tesseract-timeout 300: wait up to 5 mins
                subprocess.run(
                    ["ocrmypdf", "--skip-text", "--jobs", "4", pdf_path, temp_pdf_path],
                    check=True,
                    capture_output=True
                )
                # Use the OCR'd PDF
                pdf_path = temp_pdf_path
                print(f"DEBUG: OCR completed.")
            except subprocess.CalledProcessError as e:
                print(f"WARNING: OCRmyPDF failed: {e.stderr.decode()}. Using original PDF.")
                if os.path.exists(temp_pdf_path):
                    os.remove(temp_pdf_path)
            except Exception as e:
                print(f"WARNING: OCRmyPDF failed: {e}. Using original PDF.")

        # Extract text using pdfplumber
        import pdfplumber
        print(f"DEBUG: Extracting text with pdfplumber...")
        
        full_text = ""
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages:
                text = page.extract_text()
                if text:
                    full_text += text + "\n\n"
        
        # Clean up temp file if it exists
        if 'temp_pdf_path' in locals() and os.path.exists(temp_pdf_path):
            os.remove(temp_pdf_path)
            
        if not full_text.strip():
             return {
                "status": "error",
                "message": "No text extracted from PDF",
                "markdown_path": None,
                "goms_no": None
            }

        # Simple Markdown conversion heuristic
        markdown_content = ""
        lines = full_text.split('\n')
        
        for line in lines:
            line = line.strip()
            if not line:
                continue
                
            # Heuristic for headers
            if line.isupper() and len(line) < 100:
                if "GOVERNMENT" in line or "ORDER" in line or "NOTIFICATION" in line or "ABSTRACT" in line:
                    markdown_content += f"## {line}\n\n"
                else:
                    markdown_content += f"### {line}\n\n"
            elif line.startswith("G.O.Ms.No"):
                markdown_content += f"**{line}**\n\n"
            else:
                markdown_content += f"{line}\n\n"
        
        print(f"DEBUG: Text extracted ({len(markdown_content)} characters)")
        
        # Extract GO number from markdown for filename
        goms_no = "Unknown"
        goms_match = re.search(r'G\.O\.Ms\.No\.?\s*(\d+)', markdown_content, re.IGNORECASE)
        if goms_match:
            goms_no = goms_match.group(1)
        
        # Generate output filename
        input_filename = os.path.splitext(os.path.basename(pdf_path))[0]
        output_filename = f"{input_filename}.md"
        output_path = os.path.join(output_dir, output_filename)
        
        # Write markdown file
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(markdown_content)
        
        print(f"DEBUG: Markdown file created: {output_path}")
        
        return {
            "status": "success",
            "message": f"Successfully converted {pdf_path} to markdown",
            "markdown_path": output_path,
            "goms_no": goms_no
        }
        
    except Exception as e:
        print(f"ERROR: Error converting GO to markdown: {str(e)}")
        import traceback
        traceback.print_exc()
        return {
            "status": "error",
            "message": f"Error converting GO to markdown: {str(e)}",
            "markdown_path": None,
            "goms_no": None
        }


def convert_split_gos_to_markdown(split_result: Dict[str, Any]) -> Dict[str, Any]:
    """
    Convert all split GO PDFs to markdown files.
    
    Args:
        split_result: Result dictionary from split_goms function containing:
            - split_files: List of paths to split PDF files
            - go_index: List of GO information
    
    Returns:
        Dictionary containing:
        {
            "status": "success|error",
            "message": "Description of what happened",
            "markdown_files": List of paths to created markdown files,
            "conversion_results": List of individual conversion results
        }
    """
    print(f"DEBUG: Converting split GOs to markdown...")
    
    if split_result.get("status") != "success":
        return {
            "status": "error",
            "message": f"Cannot convert: split operation failed - {split_result.get('message')}",
            "markdown_files": [],
            "conversion_results": []
        }
    
    split_files = split_result.get("split_files", [])
    if not split_files:
        return {
            "status": "error",
            "message": "No split files found to convert",
            "markdown_files": [],
            "conversion_results": []
        }
    
    print(f"DEBUG: Found {len(split_files)} split files to convert")
    
    markdown_files = []
    conversion_results = []
    
    for i, pdf_path in enumerate(split_files, 1):
        print(f"\nConverting file {i}/{len(split_files)}: {os.path.basename(pdf_path)}")
        result = convert_go_to_markdown(pdf_path)
        conversion_results.append(result)
        
        if result["status"] == "success":
            markdown_files.append(result["markdown_path"])
            print(f"  ✓ Converted to: {os.path.basename(result['markdown_path'])}")
        else:
            print(f"  ✗ Conversion failed: {result['message']}")
    
    successful_conversions = len(markdown_files)
    total_files = len(split_files)
    
    # Print token usage summary
    from .token_tracker import TokenTracker
    TokenTracker().print_summary()
    
    if successful_conversions == 0:
        return {
            "status": "error",
            "message": f"Failed to convert any of the {total_files} split files",
            "markdown_files": [],
            "conversion_results": conversion_results
        }
    
    return {
        "status": "success",
        "message": f"Successfully converted {successful_conversions}/{total_files} GO PDFs to markdown",
        "markdown_files": markdown_files,
        "conversion_results": conversion_results
    }
