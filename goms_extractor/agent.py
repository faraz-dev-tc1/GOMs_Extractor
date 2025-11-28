from google.adk.agents import LlmAgent
from google.adk.agents import SequentialAgent
from goms_extractor.tools import parse_amendments, parse_amendments_from_markdown
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

# Amendment Parsing Agent
amendment_parser_agent = LlmAgent(
    name="amendment_parser_agent",
    model=GEMINI_MODEL,
    tools=[parse_amendments_from_markdown],  # Register the tool
    instruction="""
You are an Amendment Parsing Specialist.
Your task is to parse amendments from Government Order (GO) markdown files.

Input:
{markdown_result}

Rules:
1. Extract the list of markdown file paths from the markdown_result
2. Call the parse_amendments_from_markdown function with the markdown file paths
3. Process amendments with high accuracy
4. Return comprehensive amendment data

Output:
Return a structured report with all parsed amendments including rule numbers, types of actions, target texts, and updated texts.
""",
    description="Parses amendments from GO markdown files",
    output_key="parsed_amendments"
)

# Report Generation Agent
report_generator_agent = LlmAgent(
    name="report_generator_agent",
    model=GEMINI_MODEL,
    instruction="""
You are a GO Analysis Report Generator.
Your task is to create a comprehensive report from the parsed amendments.

Input:
{parsed_amendments}

Rules:
1. Summarize the key findings from the parsed amendments
2. Organize amendments by type (substitute, omit, add)
3. Highlight important changes or trends
4. Format the report professionally

Output:
Generate a well-structured report that summarizes the GO amendments, categorizes them by type, and highlights important changes.
""",
    description="Generates comprehensive reports from parsed amendments",
    output_key="final_report"
)

workflow_agent = SequentialAgent(
    name="goms_extraction_workflow_agent",
    sub_agents=[
        go_splitter_agent, 
        markdown_converter_agent, 
        amendment_parser_agent, 
        report_generator_agent
    ],
    description="Executes the workflow in strict sequence: Split PDFs → Convert to Markdown → Parse Amendments → Generate Report"
)

root_agent = workflow_agent