import os
import re
import json
import time
import math
import pdfplumber
from pypdf import PdfReader, PdfWriter
from dotenv import load_dotenv
import vertexai
from vertexai.generative_models import GenerativeModel, GenerationConfig

# Load environment variables
script_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(script_dir)
env_path = os.path.join(project_root, ".env")
load_dotenv(env_path)

def analyze_page_batch(pages_data: list, model: GenerativeModel) -> list:
    """
    Analyzes a batch of pages using Gemini to identify GO Start/End.
    
    Args:
        pages_data: List of tuples (page_num, text)
        model: Initialized Gemini model
        
    Returns:
        List of dicts with classification results
    """
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
        response = model.generate_content(
            prompt,
            generation_config=GenerationConfig(
                response_mime_type="application/json",
                temperature=0.1
            )
        )
        return json.loads(response.text)
    except Exception as e:
        print(f"⚠️ Batch analysis failed: {e}")
        # Return empty results for this batch to avoid crashing
        return [{"page": p[0] + 1, "is_start": False, "is_end": False, "goms_no": None} for p in pages_data]

def main():
    input_pdf = os.path.join(project_root, "data", "Amendments_OCR.pdf")
    output_dir = os.path.join(project_root, "outputs", "split_goms")
    os.makedirs(output_dir, exist_ok=True)

    # Initialize Gemini
    project_id = os.environ.get("GOOGLE_CLOUD_PROJECT")
    if not project_id:
        print("❌ GOOGLE_CLOUD_PROJECT not set.")
        return
        
    vertexai.init(project=project_id, location="asia-south1")
    model = GenerativeModel("gemini-2.0-flash-exp")

    # Load PDF
    print(f"📄 Loading PDF: {input_pdf}")
    reader = PdfReader(input_pdf)
    num_pages = len(reader.pages)
    print(f"   Total pages: {num_pages}")

    # Extract text for all pages first (faster than doing it in loop)
    print("\n📖 Extracting text...")
    all_pages_text = []
    with pdfplumber.open(input_pdf) as pdf:
        for i, page in enumerate(pdf.pages):
            all_pages_text.append((i, page.extract_text() or ""))

    # Process in batches
    BATCH_SIZE = 10
    results = []
    
    print(f"\n🤖 Analyzing pages with Gemini (Batch size: {BATCH_SIZE})...")
    total_batches = math.ceil(num_pages / BATCH_SIZE)
    
    for i in range(0, num_pages, BATCH_SIZE):
        batch = all_pages_text[i : i + BATCH_SIZE]
        print(f"   Processing batch {i//BATCH_SIZE + 1}/{total_batches} (Pages {batch[0][0]+1}-{batch[-1][0]+1})...", end="", flush=True)
        
        batch_results = analyze_page_batch(batch, model)
        results.extend(batch_results)
        print(" ✓")
        time.sleep(10) # Rate limiting for quota

    # Build Index
    print("\n📑 Building Index...")
    go_index = []
    current_go = None
    
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
                go_index.append(current_go)
            
            current_go = {
                "goms_no": goms_no or "Unknown",
                "start_page": page_num - 1, # 0-indexed
                "end_page": None # Will be set later
            }
        
        # End of GO
        if is_end and current_go:
            current_go["end_page"] = page_num - 1 # 0-indexed
            go_index.append(current_go)
            current_go = None
            
    # Handle last GO if still open
    if current_go:
        current_go["end_page"] = num_pages - 1
        go_index.append(current_go)

    print(f"   Found {len(go_index)} GOs.")

    # Split Files
    print("\n💾 Splitting PDFs...")
    for go in go_index:
        start = go["start_page"]
        end = go["end_page"]
        num = go["goms_no"]
        
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
        
        print(f"   ✓ {filename}")

    print(f"\n✅ Successfully split into {len(go_index)} files!")

if __name__ == "__main__":
    main()
