from google.adk.agents import LlmAgent, Agent
from goms_extractor.splitter import split_goms
from goms_extractor.md_converter import convert_split_gos_to_markdown
import logging

# Set up logging to see detailed output
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

GEMINI_MODEL = "gemini-2.5-flash"

# GO Splitting Agent
go_splitter_agent = LlmAgent(
    name="go_splitter_agent",
    model=GEMINI_MODEL,
    tools=[split_goms],  # Register the tool
    instruction="""
You are a Government Order (GO) Splitting Specialist.
Your task is to split a PDF containing multiple GOs into individual PDF files.

User will provide a PDF file path. Extract the file path from the user input and use it for processing.

Rules:
1. Extract the PDF path from user input
2. Call the split_goms function with the extracted PDF path
3. Verify the output directory exists or create it
4. Process only valid GO documents
5. Return a summary of the splitting results

Output:
Return a detailed report of the splitting operation including number of files created, their paths, and any issues encountered.
""",
    description="Splits PDFs containing multiple Government Orders into individual files",
    output_key="split_result"
)

# Markdown Converter Agent
markdown_converter_agent = LlmAgent(
    name="markdown_converter_agent",
    model=GEMINI_MODEL,
    tools=[convert_split_gos_to_markdown],  # Register the tool
    instruction="""
You are a Markdown Conversion Specialist.
Your task is to convert split GO PDF files into markdown format for easier processing.

Input:
{split_result}

Rules: 
1. Extract the split_result from the previous agent
2. Call the convert_split_gos_to_markdown function with the split_result
3. Ensure all PDF files are successfully converted to markdown
4. Return the list of markdown file paths

Output:
Return a detailed report of the conversion operation including the number of markdown files created and their paths.
""",
    description="Converts split GO PDFs to markdown files",
    output_key="markdown_result"
)

workflow_agent = Agent(
    name="goms_extraction_workflow_agent",
    model=GEMINI_MODEL,
    sub_agents=[
        go_splitter_agent, 
        markdown_converter_agent
    ],
    instruction="""
You are a GO Processing Workflow Orchestrator.
Your task is to coordinate the splitting and markdown conversion of Government Order PDFs.

When the user provides a PDF file path:

1. First, delegate to go_splitter_agent to split the PDF
   - If the PDF contains multiple GOs, it will be split into individual files
   - If the PDF contains only 1 GO, it will still process it (no actual splitting needed)
   
2. Then, delegate to markdown_converter_agent to convert the split PDF(s) to markdown
   - Pass the split_result from step 1 to this agent
   - This will create markdown files for all GOs

3. Finally, provide a summary to the user:
   - Number of GOs processed
   - Paths to the markdown files created
   - Location where files are saved

Handle edge cases gracefully:
- If splitting finds only 1 GO, that's fine - just proceed with conversion
- If any step fails, report the error clearly to the user

Output:
Provide a clear, concise summary of the entire process including file locations and next steps.
""",
    description="Orchestrates the GO processing workflow: Split PDFs → Convert to Markdown"
)

root_agent = workflow_agent