from pypdf import PdfReader, PdfWriter
import re
import os

input_pdf = "../data/Amendments_OCR.pdf"
output_dir = "../outputs/split_goms"

# Create output directory
os.makedirs(output_dir, exist_ok=True)

# Load PDF
reader = PdfReader(input_pdf)
num_pages = len(reader.pages)

print(f"📄 Total pages in PDF: {num_pages}\n")

# List to store (page_number, go_number, date_string)
goms_markers = []

# ROBUST pattern that handles OCR errors where O becomes 0
# Matches: G.O.Ms, G.0.Ms, G. O.Ms, G. 0.Ms, etc.
go_number_pattern = re.compile(
    r'G\.[O0]\.Ms\.No\.?\s*(\d+)',  # [O0] matches either O or 0
    re.IGNORECASE
)

# Pattern to find date
date_pattern = re.compile(
    r'Dated[:\s]+([^\n]{5,25})',
    re.IGNORECASE
)

# Scan EVERY page
for i in range(num_pages):
    text = reader.pages[i].extract_text()
    if not text:
        continue
    
    # Get first 800 characters (header area)
    header_text_upper = text[:800].upper()
    header_text_orig = text[:800]
    
    # Check if this looks like a GO document page
    # Look for GO pattern with OCR variations
    has_go_pattern = bool(re.search(r'G\.[O0]\.MS\.NO', header_text_upper))
    has_govt_header = 'GOVERNMENT OF ANDHRA PRADESH' in header_text_upper
    has_abstract = 'ABSTRACT' in header_text_upper
    
    # This is likely a new GO if it has GO pattern + government header or abstract
    if has_go_pattern and (has_govt_header or has_abstract):
        # Extract GO number from original text
        go_match = go_number_pattern.search(header_text_orig)
        
        if go_match:
            go_num = go_match.group(1)
            
            # Try to extract date
            date_match = date_pattern.search(header_text_orig)
            if date_match:
                date_str = date_match.group(1).strip()
                # Clean up date - remove extra text
                date_str = re.split(r'\s{2,}|\n', date_str)[0]
                date_clean = re.sub(r'[^\d\-A-Za-z]', '-', date_str)[:20]
            else:
                date_clean = "no-date"
            
            goms_markers.append((i, go_num, date_clean))
            print(f"✓ Found G.O.Ms.No.{go_num} on page {i + 1} (date: {date_str if date_match else 'not found'})")

print(f"\n📊 Total GOs found: {len(goms_markers)}\n")

if not goms_markers:
    raise RuntimeError("❌ No G.O.Ms. detected! Check PDF format.")

# Create page ranges
print("📑 GO Page Ranges:")
page_ranges = []
for idx, (start_page, goms_num, date_clean) in enumerate(goms_markers):
    if idx == len(goms_markers) - 1:
        end_page = num_pages - 1
    else:
        end_page = goms_markers[idx + 1][0] - 1
    
    num_pages_in_go = end_page - start_page + 1
    page_ranges.append((start_page, end_page, goms_num, date_clean))
    print(f"   GO {goms_num:>3}: pages {start_page+1:>2}-{end_page+1:>2} ({num_pages_in_go} page{'s' if num_pages_in_go > 1 else ''})")

# Split and save
print("\n💾 Splitting PDFs...")
for start, end, num, date in page_ranges:
    writer = PdfWriter()
    
    for p in range(start, end + 1):
        writer.add_page(reader.pages[p])
    
    # Create safe filename
    filename = f"GO_{num}_Dated_{date}.pdf"
    filename = re.sub(r'[<>:"/\\|?*]', '_', filename)
    output_path = os.path.join(output_dir, filename)
    
    with open(output_path, "wb") as f:
        writer.write(f)
    
    print(f"   ✓ {filename}")

print(f"\n✅ Successfully split into {len(page_ranges)} GO files!")
print(f"📁 Output directory: {output_dir}")

# Summary by page count
single_page = sum(1 for s, e, _, _ in page_ranges if e - s == 0)
multi_page = len(page_ranges) - single_page
print(f"\n📈 Summary: {single_page} single-page GOs, {multi_page} multi-page GOs")
