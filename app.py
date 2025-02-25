import streamlit as st
import zipfile
import io
import re
import chardet
import base64
from typing import List, Optional
import anthropic
import json
import os

st.set_page_config(
    page_title="Code Repository to LLM.txt Converter",
    page_icon="📄",
    layout="wide",
)

# Initialize session state for API key
if "api_key" not in st.session_state:
    st.session_state.api_key = ""
if "llm_text" not in st.session_state:
    st.session_state.llm_text = ""

def get_default_extensions() -> List[str]:
    """Returns the default list of extensions to exclude."""
    return [
        '.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tiff', '.ico',
        '.svg', '.webp', '.heic', '.raw', '.cr2', '.nef', '.psd',
        '.ai', '.pdf', '.mp3', '.mp4', '.avi', '.mov', '.wmv',
        '.flv', '.mkv', '.wav', '.ogg', '.zip', '.rar', '.7z',
        '.tar', '.gz', '.exe', '.dll', '.so', '.dylib', '.class'
    ]

def get_default_patterns() -> List[str]:
    """Returns the default list of regex patterns to filter."""
    return [
        r'^\s*\{file\s*=.*,\s*hash\s*=.*\}',   # Package file hash entries
        r'^\s*"sha\d+:.*",?$',                 # SHA hash lines
        r'^\s*[a-f0-9]{40,}\s*$',              # Plain hash lines
        r'.*\.whl",\s*hash\s*=\s*"sha.*$',     # Wheel file references with hashes
        r'^\s*"[^"]+\.(whl|tar\.gz)".*$',      # Package file references
    ]

def create_download_link(file_content, file_name):
    """Creates a download link for the generated file."""
    b64 = base64.b64encode(file_content.encode()).decode()
    return f'<a href="data:text/plain;base64,{b64}" download="{file_name}">Download {file_name}</a>'

def extract_svg_from_response(response_content):
    """Extract SVG content from the API response using regex."""
    svg_pattern = r'<svg.*?>(.*?)</svg>'
    match = re.search(svg_pattern, response_content, re.DOTALL)
    
    if match:
        svg_content = f'<svg>{match.group(1)}</svg>'
        return svg_content
    return None

def extract_summary_from_response(response_content):
    """Extract summary content from the API response using regex."""
    summary_pattern = r'<summary>(.*?)</summary>'
    match = re.search(summary_pattern, response_content, re.DOTALL)
    
    if match:
        return match.group(1).strip()
    return None

def generate_svg_from_llm_text(llm_text, api_key):
    """Generate an SVG representation of the code repository using Anthropic API."""
    try:
        client = anthropic.Anthropic(api_key=api_key)
        
        system_prompt = """You are tasked with analyzing a code repository and creating a correct and easy-to-read overview of the entire repo or service as an SVG. This overview should provide a clear visual representation of the repository's structure, main components, and their relationships.

First, carefully examine the provided code repository:

<code_repo>
{code_repo}
</code_repo>

To analyze the repository, follow these steps:

1. Identify the main components of the repository (e.g., directories, key files, modules, services).
2. Determine the relationships and dependencies between these components.
3. Note any important patterns or architectural decisions evident in the code structure.
4. Identify the primary programming language(s) used and any significant frameworks or libraries.

Now, create an SVG overview of the repository using the following guidelines:

1. Use appropriate shapes to represent different types of components (e.g., rectangles for directories, rounded rectangles for files, hexagons for services).
2. Arrange the components in a logical hierarchy that reflects the repository's structure.
3. Use arrows or lines to show relationships and dependencies between components.
4. Include brief labels for each component to clearly identify its purpose or name.
5. Use color coding to distinguish between different types of components or to highlight important elements.
6. Ensure the SVG is scalable and readable at different sizes.

When creating the SVG, follow these best practices:

1. Keep the design clean and minimalistic to enhance readability.
2. Use a consistent style throughout the diagram.
3. Limit the use of text to essential information only.
4. Ensure there is enough white space to prevent the diagram from looking cluttered.

Your final output should consist of:

1. A brief textual summary (2-3 sentences) describing the main features of the repository.
2. The SVG code for the overview diagram.

Present your final output in the following format:

<summary>
[Insert your brief textual summary here]
</summary>

<svg>
[Insert your SVG code here]
</svg>

Remember, your output should only include the summary and SVG code as specified above. Do not include any additional explanations, notes, or the steps you took to create the overview."""
        
        # Replace placeholder with actual code repository content
        system_prompt = system_prompt.replace("{code_repo}", llm_text)
        
        message = client.messages.create(
            model="claude-3-7-sonnet-20250219",
            max_tokens=64000,
            temperature=0.7,
            system=system_prompt,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": "Create the overview for the new repo"
                        }
                    ]
                }
            ]
        )
        
        response_content = message.content[0].text
        
        # Extract the SVG and summary from the response
        svg_content = extract_svg_from_response(response_content)
        summary = extract_summary_from_response(response_content)
        
        return {
            "success": True,
            "svg": svg_content,
            "summary": summary,
            "full_response": response_content
        }
        
    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }

def process_zip_to_llm_txt(
    zip_file,
    max_chars: Optional[int] = None, 
    exclude_extensions: Optional[List[str]] = None, 
    filter_patterns: Optional[List[str]] = None, 
    max_lines_per_file: Optional[int] = None
) -> tuple:
    """
    Process a zip file and convert it to LLM.txt.
    
    Returns:
        tuple: (status, llm_text, stats)
    """
    if exclude_extensions is None:
        exclude_extensions = get_default_extensions()
        
    if filter_patterns is None:
        filter_patterns = get_default_patterns()
    
    if not zip_file:
        return False, "", {"error": "No file was uploaded."}
    
    try:
        # Open the zip file
        with zipfile.ZipFile(io.BytesIO(zip_file.getvalue()), 'r') as zip_ref:
            # Get all file names in the zip, excluding directories and excluded extensions
            file_list = sorted([
                f for f in zip_ref.namelist() 
                if not f.endswith('/') and not any(f.lower().endswith(ext) for ext in exclude_extensions)
            ])
            
            # Count excluded files
            all_files = [f for f in zip_ref.namelist() if not f.endswith('/')]
            excluded_files = [f for f in all_files if any(f.lower().endswith(ext) for ext in exclude_extensions)]
            
            total_files = len(file_list)
            stats = {
                "total_files": len(all_files),
                "excluded_files": len(excluded_files),
                "processed_files": total_files,
                "errors": [],
                "total_chars": 0,
                "truncated": False
            }
            
            # Create output text
            output_text = ""
            total_chars = 0
            max_reached = False
            
            # Process progress bar
            progress_bar = st.progress(0)
            status_text = st.empty()
            
            # Process each file
            for i, file_path in enumerate(file_list):
                try:
                    # Update progress
                    progress = (i + 1) / total_files
                    progress_bar.progress(progress)
                    status_text.text(f"Processing file {i + 1}/{total_files}: {file_path}")
                    
                    # Read file content
                    content = zip_ref.read(file_path)
                    
                    # Try to detect encoding
                    encoding_result = chardet.detect(content)
                    encoding = encoding_result['encoding'] if encoding_result['encoding'] else 'utf-8'
                    
                    try:
                        decoded_content = content.decode(encoding)
                    except UnicodeDecodeError:
                        # Fall back to utf-8 with errors ignored if detection fails
                        decoded_content = content.decode('utf-8', errors='replace')
                    
                    # Apply line filtering if needed
                    if filter_patterns and len(filter_patterns) > 0:
                        # Combine all patterns with OR
                        combined_pattern = '|'.join(f'({pattern})' for pattern in filter_patterns)
                        regex = re.compile(combined_pattern)
                        
                        # Split by lines, filter, and rejoin
                        lines = decoded_content.splitlines()
                        filtered_lines = [line for line in lines if not regex.match(line)]
                        
                        # Apply max lines limit if specified
                        if max_lines_per_file and len(filtered_lines) > max_lines_per_file:
                            # Take a mix of lines from beginning, middle, and end
                            beginning = max_lines_per_file // 3
                            end = max_lines_per_file // 3
                            middle = max_lines_per_file - beginning - end
                            
                            if middle > 0:
                                middle_start = (len(filtered_lines) - middle) // 2
                                selected_lines = (
                                    filtered_lines[:beginning] + 
                                    ['...'] + 
                                    filtered_lines[middle_start:middle_start + middle] + 
                                    ['...'] + 
                                    filtered_lines[-end:]
                                )
                            else:
                                selected_lines = filtered_lines[:beginning] + ['...'] + filtered_lines[-end:]
                            
                            filtered_lines = selected_lines
                        
                        decoded_content = '\n'.join(filtered_lines)
                    
                    # Create header
                    header = f"{'=' * 48}\nFile: {file_path}\n{'=' * 48}\n"
                    
                    # Check if adding this content would exceed max_chars
                    content_length = len(header) + len(decoded_content)
                    if max_chars and (total_chars + content_length > max_chars):
                        remaining = max_chars - total_chars
                        if remaining > len(header):
                            # Add truncated content
                            output_text += header
                            output_text += decoded_content[:remaining - len(header)]
                            output_text += "\n\n[Content truncated due to size limit]\n"
                        else:
                            # Can't even fit the header
                            output_text += "\n\n[Remaining files omitted due to size limit]\n"
                        max_reached = True
                        stats["truncated"] = True
                        break
                    
                    # Add to output text
                    output_text += header
                    output_text += decoded_content
                    output_text += "\n\n"
                    
                    total_chars += content_length
                
                except Exception as e:
                    error_msg = f"Error processing {file_path}: {str(e)}"
                    stats["errors"].append(error_msg)
            
            # Update final stats
            stats["total_chars"] = total_chars
            
            # Clear progress indicators
            progress_bar.empty()
            status_text.empty()
            
            return True, output_text, stats
            
    except Exception as e:
        return False, "", {"error": f"Error processing zip file: {str(e)}"}

def main():
    st.title("Code Repository to LLM.txt Converter")
    st.markdown("""
    This tool converts a code repository (ZIP file) into a single text file format for use with Large Language Models.
    It can filter out binary files, limit file sizes, and remove unnecessary content to make the output more useful.
    """)
    
    # Sidebar configuration
    st.sidebar.header("Configuration")
    
    max_chars = st.sidebar.number_input(
        "Maximum Characters", 
        min_value=10000, 
        max_value=10000000, 
        value=300000,
        help="Maximum total characters to include in the output file"
    )
    
    max_lines = st.sidebar.number_input(
        "Maximum Lines Per File", 
        min_value=50, 
        max_value=10000, 
        value=500,
        help="Maximum number of lines to include from each file"
    )
    
    # Extensions to exclude
    st.sidebar.subheader("Extensions to Exclude")
    
    default_extensions = get_default_extensions()
    extensions_text = st.sidebar.text_area(
        "Enter extensions to exclude (one per line)", 
        value="\n".join(default_extensions),
        height=150
    )
    exclude_extensions = [ext.strip() for ext in extensions_text.split("\n") if ext.strip()]
    
    # Advanced options
    show_advanced = st.sidebar.checkbox("Show Advanced Options")
    
    filter_patterns = get_default_patterns()
    if show_advanced:
        st.sidebar.subheader("Filter Patterns")
        patterns_text = st.sidebar.text_area(
            "Enter regex patterns to filter (one per line)", 
            value="\n".join(filter_patterns),
            height=150
        )
        filter_patterns = [pattern.strip() for pattern in patterns_text.split("\n") if pattern.strip()]
        
        # Anthropic API Key (optional)
        st.sidebar.subheader("Anthropic API Integration")
        api_key = st.sidebar.text_input(
            "Anthropic API Key (optional)",
            type="password",
            help="Enter your Anthropic API key to enable repository visualization"
        )
        
        # Store API key in session state
        if api_key != st.session_state.api_key:
            st.session_state.api_key = api_key
    else:
        # If advanced options are hidden, still maintain the API key state
        api_key = st.session_state.get("api_key", "")
    
    # Main content area
    upload_placeholder = st.empty()
    uploaded_file = upload_placeholder.file_uploader("Upload ZIP file containing your code repository", type="zip")
    
    if uploaded_file:
        st.subheader("Processing ZIP File")
        
        with st.spinner("Processing repository..."):
            success, llm_text, stats = process_zip_to_llm_txt(
                uploaded_file,
                max_chars=max_chars, 
                exclude_extensions=exclude_extensions,
                filter_patterns=filter_patterns,
                max_lines_per_file=max_lines
            )
        
        if success:
            st.success("Processing complete!")
            
            # Store the llm_text in session state for later use
            st.session_state.llm_text = llm_text
            
            # Display stats
            st.subheader("Processing Statistics")
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("Total Files", stats["total_files"])
            with col2:
                st.metric("Excluded Files", stats["excluded_files"])
            with col3:
                st.metric("Processed Files", stats["processed_files"])
            
            st.metric("Total Characters", stats["total_chars"])
            
            if stats.get("truncated"):
                st.warning(f"Content was truncated to {max_chars} characters.")
            
            if stats.get("errors"):
                with st.expander("Processing Errors"):
                    for error in stats["errors"]:
                        st.error(error)
            
            # Preview
            with st.expander("Preview (first 5000 characters)"):
                st.text(llm_text[:5000] + ("..." if len(llm_text) > 5000 else ""))
            
            # Download button
            st.subheader("Download Result")
            download_link = create_download_link(llm_text, "llm.txt")
            st.markdown(download_link, unsafe_allow_html=True)
            
            # Visualization option with Anthropic API
            st.subheader("Repository Visualization")
            
            if st.button("Generate Repository Overview"):
                if not st.session_state.api_key:
                    st.error("Anthropic API Key is required for visualization. Please enter your API key in the sidebar under 'Advanced Options'.")
                else:
                    with st.spinner("Generating repository visualization... This may take a minute or two."):
                        result = generate_svg_from_llm_text(llm_text, st.session_state.api_key)
                        
                        if result["success"]:
                            if result["summary"]:
                                st.markdown("### Repository Summary")
                                st.markdown(result["summary"])
                            
                            if result["svg"]:
                                st.markdown("### Repository Diagram")
                                st.markdown(result["svg"], unsafe_allow_html=True)
                                
                                # Also provide a download for the SVG
                                svg_download = create_download_link(result["svg"], "repository_overview.svg")
                                st.markdown("Download the SVG file: " + svg_download, unsafe_allow_html=True)
                            else:
                                st.error("No SVG content found in the API response.")
                                with st.expander("See full API response"):
                                    st.text(result["full_response"])
                        else:
                            st.error(f"Error generating visualization: {result.get('error', 'Unknown error')}")
            
            # Option to process another file
            if st.button("Process Another File"):
                upload_placeholder.empty()
                st.rerun()  # Using st.rerun() instead of deprecated st.experimental_rerun()
        else:
            st.error(f"Error: {stats.get('error', 'Unknown error')}")

if __name__ == "__main__":
    main()
