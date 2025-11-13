from pypdf import PdfReader, PdfWriter
import ocrmypdf
import re
import os

input_pdf = "Amendments_OCR.pdf"
output_dir = "split_goms"

# Create output directory
os.makedirs(output_dir, exist_ok=True)

# Load PDF
reader = PdfReader(input_pdf)
num_pages = len(reader.pages)

# List to store (start_page, goms_number, date)
goms_markers = []

# Robust regex to match G.O.Ms. even with formatting quirks
goms_pattern = re.compile(
    r'G\.O\.Ms\.No\.?\s*(\d+)'          # Matches "G.O.Ms.No.476", "G.O.Ms.No 476", etc.
    r'.*?'                              # Non-greedy skip
    r'Dated[：:]\s*([\d\-JulyMayetc]+)', # Match Dated： or Dated: + date (flexible)
    re.IGNORECASE | re.DOTALL
)

# Scan each page
for i in range(num_pages):
    text = reader.pages[i].extract_text()
    if not text:
        continue
    # Normalize full-width colon to standard colon for consistency (optional)
    text = text.replace('：', ':')
    
    match = goms_pattern.search(text)
    if match:
        goms_num = match.group(1)
        date_str = match.group(2).strip()
        # Clean date (remove extra spaces, fix "14t July" → keep as-is or normalize)
        date_clean = re.sub(r'[^0-9A-Za-z\-]', '', date_str)[:10]  # crude but safe
        goms_markers.append((i, goms_num, date_clean))
        print(f"Found G.O.Ms.No.{goms_num} on page {i + 1} (date: {date_str})")

if not goms_markers:
    raise RuntimeError("No G.O.Ms. detected! Check PDF format.")

# Add final page as end boundary
page_ranges = []
for idx, (start_page, goms_num, date_clean) in enumerate(goms_markers):
    if idx == len(goms_markers) - 1:
        end_page = num_pages - 1
    else:
        end_page = goms_markers[idx + 1][0] - 1
    page_ranges.append((start_page, end_page, goms_num, date_clean))

# Now split
for start, end, num, date in page_ranges:
    writer = PdfWriter()
    for p in range(start, end + 1):
        writer.add_page(reader.pages[p])
    
    # Safe filename
    filename = f"G.O.Ms.No.{num}_Dated_{date}.pdf"
    # Remove invalid characters
    filename = re.sub(r'[<>:"/\\|?*]', '_', filename)
    output_path = os.path.join(output_dir, filename)
    
    with open(output_path, "wb") as f:
        writer.write(f)
    print(f"Saved: {output_path}")

print(f"\n✅ Successfully split into {len(page_ranges)} files in '{output_dir}' folder.")
