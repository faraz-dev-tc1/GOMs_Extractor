"""
Markdown converter for Government Orders (GOs).
Converts split GO PDFs into markdown files for easier processing.
"""

import os
import re
from typing import Dict, Any, List
from dotenv import load_dotenv
import vertexai
from vertexai.generative_models import GenerativeModel, GenerationConfig, Part


def convert_go_to_markdown(pdf_path: str, output_dir: str = None) -> Dict[str, Any]:
    """
    Convert a single GO PDF file to markdown format.
    
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
    print(f"DEBUG: Converting PDF to markdown: {pdf_path}")
    try:
        # Set default output directory
        if output_dir is None:
            script_dir = os.path.dirname(os.path.abspath(__file__))
            project_root = os.path.dirname(script_dir)
            output_dir = os.path.join(project_root, "outputs", "markdown_goms")
        
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
            return {
                "status": "error",
                "message": "GOOGLE_CLOUD_PROJECT environment variable not set",
                "markdown_path": None,
                "goms_no": None
            }
        
        print(f"DEBUG: Initializing Vertex AI with project: {project_id}")
        vertexai.init(project=project_id, location="asia-south1")
        model = GenerativeModel("gemini-2.5-flash")
        print(f"DEBUG: Gemini model initialized")
        
        # Read PDF as bytes
        with open(pdf_path, "rb") as f:
            pdf_data = f.read()
        
        # Create PDF part
        pdf_part = Part.from_data(pdf_data, mime_type="application/pdf")
        
        # Prompt for markdown conversion
        prompt = """Convert this Government Order (GO) PDF document to well-structured markdown format.

INSTRUCTIONS:
1. Extract ALL text content from the PDF
2. Preserve the document structure and hierarchy
3. Use proper markdown formatting:
   - Use # for main headings (e.g., GOVERNMENT OF ANDHRA PRADESH)
   - Use ## for section headings (e.g., ABSTRACT, NOTIFICATION, AMENDMENTS)
   - Use ### for sub-sections
   - Use **bold** for important labels like "G.O.Ms.No.", "Dated:", etc.
   - Use bullet points or numbered lists where appropriate
   - Use blockquotes (>) for quoted text or references
4. Maintain the original text exactly as it appears
5. Include all sections: header, abstract, references, notification, amendments, signature

OUTPUT FORMAT:
Return ONLY the markdown content, no explanations or additional text."""

        print(f"DEBUG: Sending conversion request to Gemini...")
        response = model.generate_content(
            [prompt, pdf_part],
            generation_config=GenerationConfig(
                temperature=0.1,
                max_output_tokens=8192
            )
        )
        
        markdown_content = response.text.strip()
        print(f"DEBUG: Markdown content generated ({len(markdown_content)} characters)")
        
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
