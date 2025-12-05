"""
Markdown converter for Government Orders (GOs).
Converts split GO PDFs into markdown files using Vertex AI Gemini 2.5-flash.
"""

import os
import re
from typing import Dict, Any, List, Optional
from dotenv import load_dotenv
import vertexai
from vertexai.generative_models import GenerativeModel, Part
import base64

# Load environment variables
load_dotenv()


def convert_go_to_markdown(pdf_path: str, output_dir: Optional[str] = None) -> Dict[str, Any]:
    """
    Convert a single GO PDF file to markdown format using Vertex AI Gemini 2.5-flash.
    
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
    print(f"DEBUG: Converting PDF to markdown using Gemini 2.5-flash: {pdf_path}")
    try:
        # Set default output directory
        if output_dir is None:
            script_dir = os.path.dirname(os.path.abspath(__file__))
            project_root = os.path.dirname(script_dir)
            output_dir = os.path.join(project_root, "outputs", "markdown_goms")
        
        os.makedirs(output_dir, exist_ok=True)
        print(f"DEBUG: Output directory created/verified: {output_dir}")
        
        # Initialize Vertex AI
        project_id = os.getenv("GOOGLE_CLOUD_PROJECT")
        location = os.getenv("GOOGLE_CLOUD_REGION", "us-central1")
        
        if not project_id:
            return {
                "status": "error",
                "message": "GOOGLE_CLOUD_PROJECT environment variable not set",
                "markdown_path": None,
                "goms_no": None
            }
        
        print(f"DEBUG: Initializing Vertex AI (project: {project_id}, location: {location})")
        vertexai.init(project=project_id, location=location)
        
        # Initialize Gemini model
        model = GenerativeModel("gemini-2.0-flash-exp")
        print(f"DEBUG: Gemini model initialized")
        
        # Read PDF file as bytes
        with open(pdf_path, 'rb') as f:
            pdf_bytes = f.read()
        
        # Create PDF part for Gemini
        pdf_part = Part.from_data(
            data=pdf_bytes,
            mime_type="application/pdf"
        )
        
        # Create prompt for markdown conversion
        prompt = """Convert this Government Order (GO) PDF document into well-formatted markdown.

Instructions:
1. Extract ALL text content from the document
2. Preserve the document structure and hierarchy
3. Use appropriate markdown formatting:
   - Use ## for main headings (GOVERNMENT, ORDER, NOTIFICATION, ABSTRACT, etc.)
   - Use ### for sub-headings
   - Use **bold** for important elements like G.O.Ms.No
   - Preserve tables, lists, and formatting
4. Maintain the original text exactly as it appears
5. Include all dates, numbers, and official references
6. Do not add any commentary or explanations
7. Return ONLY the markdown content, no additional text

Output the complete markdown representation of this document."""

        print(f"DEBUG: Sending PDF to Gemini for conversion...")
        
        # Generate content using Gemini
        response = model.generate_content(
            [prompt, pdf_part],
            generation_config={
                "temperature": 0.0,
                "max_output_tokens": 8192,
            }
        )
        
        # Extract markdown content from response
        if not response.text:
            return {
                "status": "error",
                "message": "No content extracted from PDF by Gemini",
                "markdown_path": None,
                "goms_no": None
            }
        
        markdown_content = response.text.strip()
        print(f"DEBUG: Markdown extracted ({len(markdown_content)} characters)")
        
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
        
        # Track token usage if tracker is available
        try:
            from .token_tracker import TokenTracker
            tracker = TokenTracker()
            tracker.track_response(response, context="convert_go_to_markdown")
        except Exception as e:
            print(f"DEBUG: Token tracking not available: {e}")
        
        return {
            "status": "success",
            "message": f"Successfully converted {pdf_path} to markdown using Gemini 2.5-flash",
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



def convert_split_gos_to_markdown(split_result: Dict[str, Any], output_dir: Optional[str] = None, max_workers: int = 4) -> Dict[str, Any]:
    """
    Convert all split GO PDFs to markdown files concurrently.
    
    Args:
        split_result: Result dictionary from split_goms function containing:
            - split_files: List of paths to split PDF files
            - go_index: List of GO information
        output_dir: Optional output directory for markdown files
        max_workers: Maximum number of concurrent workers (default: 4)
    
    Returns:
        Dictionary containing:
        {
            "status": "success|error",
            "message": "Description of what happened",
            "markdown_files": List of paths to created markdown files,
            "conversion_results": List of individual conversion results
        }
    """
    print(f"DEBUG: Converting split GOs to markdown (concurrent with {max_workers} workers)...")
    
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
    
    # Use ThreadPoolExecutor for concurrent processing
    from concurrent.futures import ThreadPoolExecutor, as_completed
    
    markdown_files = []
    conversion_results = [None] * len(split_files)  # Preserve order
    
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        # Submit all conversion tasks
        future_to_index = {
            executor.submit(convert_go_to_markdown, pdf_path, output_dir): (i, pdf_path)
            for i, pdf_path in enumerate(split_files)
        }
        
        # Process results as they complete
        completed = 0
        for future in as_completed(future_to_index):
            i, pdf_path = future_to_index[future]
            completed += 1
            
            try:
                result = future.result()
                conversion_results[i] = result
                
                print(f"\nCompleted {completed}/{len(split_files)}: {os.path.basename(pdf_path)}")
                
                if result["status"] == "success":
                    markdown_files.append(result["markdown_path"])
                    print(f"  ✓ Converted to: {os.path.basename(result['markdown_path'])}")
                else:
                    print(f"  ✗ Conversion failed: {result['message']}")
            except Exception as e:
                print(f"  ✗ Exception during conversion: {str(e)}")
                conversion_results[i] = {
                    "status": "error",
                    "message": f"Exception during conversion: {str(e)}",
                    "markdown_path": None,
                    "goms_no": None
                }
    
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
        "message": f"Successfully converted {successful_conversions}/{total_files} GO PDFs to markdown (concurrent processing)",
        "markdown_files": markdown_files,
        "conversion_results": conversion_results
    }
