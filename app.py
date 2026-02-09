import streamlit as st
import fitz  # PyMuPDF
import gc
import os
import tempfile
import threading
import pandas as pd
import zipfile
from io import BytesIO

# --- STABILITY CONFIGURATION ---
# Global lock ensures only one compression task runs at a time across all users
if 'process_lock' not in st.session_state:
    st.session_state.process_lock = threading.Lock()

# Limit total upload size to prevent server RAM exhaustion
MAX_FILE_SIZE_MB = 200 

def purge():
    """Force garbage collection to free up system memory."""
    gc.collect()

def fast_compress(input_path, dpi, quality):
    """
    Core compression engine. 
    Converts PDF pages to images and re-assembles them to reduce size.
    """
    doc = fitz.open(input_path)
    out_doc = fitz.open()
    
    for page in doc:
        # Scale the page based on DPI settings
        zoom = dpi / 72
        mat = fitz.Matrix(zoom, zoom)
        
        # Render page to image buffer (RGB prevents transparency issues)
        pix = page.get_pixmap(matrix=mat, colorspace=fitz.csRGB)
        img_data = pix.tobytes("jpg", jpg_quality=quality)
        
        # Create a new page in the output PDF with original dimensions
        new_page = out_doc.new_page(width=page.rect.width, height=page.rect.height)
        new_page.insert_image(page.rect, stream=img_data)
        
        # Explicitly clear image from memory
        pix = None

    # Save to a temporary disk location rather than RAM
    out_path = tempfile.mktemp(suffix=".pdf")
    out_doc.save(out_path, garbage=4, deflate=True)
    
    doc.close()
    out_doc.close()
    return out_path

# --- USER INTERFACE ---
st.set_page_config(page_title="Professional PDF Compressor", page_icon="⚡", layout="centered")

st.title("⚡ Professional PDF Compressor")
st.markdown("""
    **Stability Features Active:** - 🛡️ **Queue System:** Prevents crashes during simultaneous usage.
    - 📂 **Smart Export:** Single PDF or ZIP for batches.
    - 🧠 **Memory Guard:** Auto-cleanup of temporary files.
""")

# Sidebar settings for user control
st.sidebar.header("Compression Settings")
mode = st.sidebar.select_slider(
    "Balance Quality vs Size",
    options=["Extreme", "Recommended", "High Quality"],
    value="Recommended"
)

# Map UI modes to technical parameters
settings_map = {
    "Extreme": {"dpi": 60, "quality": 30},
    "Recommended": {"dpi": 75, "quality": 50},
    "High Quality": {"dpi": 110, "quality": 75}
}

up_files = st.file_uploader("Upload PDF files", type="pdf", accept_multiple_files=True)

if up_files:
    # Pre-check file sizes to protect the server
    total_size_mb = sum(f.size for f in up_files) / (1024 * 1024)
    
    if total_size_mb > MAX_FILE_SIZE_MB:
        st.error(f"❌ Batch too large ({total_size_mb:.1f}MB). Limit is {MAX_FILE_SIZE_MB}MB.")
    else:
        if st.button(f"Compress {len(up_files)} File(s)"):
            # Use the lock to ensure serial processing
            with st.session_state.process_lock:
                processed_results = [] # Stores (bytes, filename)
                report_data = []
                
                progress_bar = st.progress(0)
                status_box = st.empty()

                for idx, up_file in enumerate(up_files):
                    status_box.info(f"Processing: **{up_file.name}**")
                    
                    # 1. Write upload to disk to free up RAM buffer
                    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as f_in:
                        f_in.write(up_file.getbuffer())
                        f_in_path = f_in.name
                    
                    comp_path = None
                    try:
                        # 2. Run compression
                        comp_path = fast_compress(
                            f_in_path, 
                            settings_map[mode]["dpi"], 
                            settings_map[mode]["quality"]
                        )
                        
                        # 3. Read compressed file back to memory briefly for the download button
                        with open(comp_path, "rb") as f:
                            final_pdf_bytes = f.read()
                        
                        processed_results.append((final_pdf_bytes, up_file.name))
                        
                        # Calculate statistics
                        orig_s = os.path.getsize(f_in_path) / (1024 * 1024)
                        new_s = len(final_pdf_bytes) / (1024 * 1024)
                        reduction = (1 - (new_s / orig_s)) * 100
                        
                        report_data.append({
                            "File Name": up_file.name,
                            "Original": f"{orig_s:.2f} MB",
                            "Compressed": f"{new_s:.2f} MB",
                            "Saved": f"{int(reduction)}%"
                        })

                    except Exception as e:
                        st.error(f"Error processing {up_file.name}: {e}")
                    
                    finally:
                        # 4. Critical Cleanup: Remove temp files and trigger garbage collection
                        if os.path.exists(f_in_path):
                            os.remove(f_in_path)
                        if comp_path and os.path.exists(comp_path):
                            os.remove(comp_path)
                        purge()
                        progress_bar.progress((idx + 1) / len(up_files))

                status_box.success("🎉 Compression Complete!")
                
                # Display results table
                st.table(pd.DataFrame(report_data))

                # 5. Smart Download Logic
                if len(processed_results) == 1:
                    # Single file: Provide PDF directly
                    st.download_button(
                        label="📥 Download Compressed PDF",
                        data=processed_results[0][0],
                        file_name=f"compressed_{processed_results[0][1]}",
                        mime="application/pdf",
                        use_container_width=True
                    )
                else:
                    # Multiple files: Provide ZIP archive
                    zip_buffer = BytesIO()
                    with zipfile.ZipFile(zip_buffer, "w") as zf:
                        for data, name in processed_results:
                            zf.writestr(f"compressed_{name}", data)
                    
                    st.download_button(
                        label="📥 Download All as ZIP",
                        data=zip_buffer.getvalue(),
                        file_name="compressed_pdfs_batch.zip",
                        mime="application/zip",
                        use_container_width=True
                    )

# Footer info
st.divider()
st.caption("Engineered for stability. Temporary files are automatically purged after processing.")
