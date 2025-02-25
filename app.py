import streamlit as st
import zipfile
import io
import re
import chardet
import base64
from typing import List, Optional

st.set_page_config(
    page_title="Code Repository to LLM.txt Converter",
    page_icon="📄",
    layout="wide",
)

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
            
            # Option to process another file
            if st.button("Process Another File"):
                upload_placeholder.empty()
                st.rerun()  # Using st.rerun() instead of deprecated st.experimental_rerun()
        else:
            st.error(f"Error: {stats.get('error', 'Unknown error')}")

if __name__ == "__main__":
    main()
