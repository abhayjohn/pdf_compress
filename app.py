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
if 'process_lock' not in st.session_state:
    st.session_state.process_lock = threading.Lock()

MAX_FILE_SIZE_MB = 500 

def purge():
    gc.collect()

def fast_compress(input_path, dpi, quality):
    doc = fitz.open(input_path)
    out_doc = fitz.open()
    
    for page in doc:
        # zoom = dpi / 72. 72 is the internal PDF point system.
        zoom = dpi / 72
        mat = fitz.Matrix(zoom, zoom)
        
        # Capture the page as an image
        pix = page.get_pixmap(matrix=mat, colorspace=fitz.csRGB)
        img_data = pix.tobytes("jpg", jpg_quality=quality)
        
        # Re-insert into a clean PDF page
        new_page = out_doc.new_page(width=page.rect.width, height=page.rect.height)
        new_page.insert_image(page.rect, stream=img_data)
        
        pix = None # Release image from RAM

    out_path = tempfile.mktemp(suffix=".pdf")
    out_doc.save(out_path, garbage=4, deflate=True)
    
    doc.close()
    out_doc.close()
    return out_path

# --- UI ---
st.set_page_config(page_title="Custom PDF Compressor", page_icon="⚙️")

st.title("⚙️ Custom PDF Compressor")
st.info(f"Max Capacity: {MAX_FILE_SIZE_MB}MB per batch. Processing is queued.")

# --- DUAL SLIDER SIDEBAR ---
st.sidebar.header("Compression Tuning")

# Slider 1: Resolution (DPI)
user_dpi = st.sidebar.slider(
    "Resolution (DPI)", 
    min_value=50, 
    max_value=200, 
    value=90, 
    step=10,
    help="Higher DPI makes text and lines sharper but increases file size significantly."
)

# Slider 2: JPEG Quality
user_quality = st.sidebar.slider(
    "Image Quality (%)", 
    min_value=10, 
    max_value=100, 
    value=60, 
    step=5,
    help="Lower quality increases 'graininess' in photos but saves a lot of space."
)

# Technical Status Update
st.sidebar.divider()
st.sidebar.write(f"**Target Resolution:** {user_dpi} DPI")
st.sidebar.write(f"**Compression Level:** {100 - user_quality}% Reduction")



up_files = st.file_uploader("Upload PDF files", type="pdf", accept_multiple_files=True)

if up_files:
    total_size_mb = sum(f.size for f in up_files) / (1024 * 1024)
    
    if total_size_mb > MAX_FILE_SIZE_MB:
        st.error(f"❌ Total size ({total_size_mb:.1f}MB) exceeds limit.")
    else:
        if st.button(f"Compress {len(up_files)} File(s)"):
            with st.session_state.process_lock:
                processed_results = []
                report_data = []
                
                progress_bar = st.progress(0)
                status_box = st.empty()

                for idx, up_file in enumerate(up_files):
                    status_box.info(f"Working on: **{up_file.name}**")
                    
                    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as f_in:
                        f_in.write(up_file.getbuffer())
                        f_in_path = f_in.name
                    
                    comp_path = None
                    try:
                        # Use the custom slider values here
                        comp_path = fast_compress(f_in_path, user_dpi, user_quality)
                        
                        with open(comp_path, "rb") as f:
                            final_pdf_bytes = f.read()
                        
                        processed_results.append((final_pdf_bytes, up_file.name))
                        
                        orig_s = os.path.getsize(f_in_path) / (1024 * 1024)
                        new_s = len(final_pdf_bytes) / (1024 * 1024)
                        
                        report_data.append({
                            "File Name": up_file.name,
                            "Original": f"{orig_s:.2f} MB",
                            "New": f"{new_s:.2f} MB",
                            "Reduction": f"{int((1 - new_s/orig_s)*100)}%"
                        })

                    except Exception as e:
                        st.error(f"Error on {up_file.name}: {e}")
                    
                    finally:
                        if os.path.exists(f_in_path): os.remove(f_in_path)
                        if comp_path and os.path.exists(comp_path): os.remove(comp_path)
                        purge()
                        progress_bar.progress((idx + 1) / len(up_files))

                status_box.success("✅ Process complete!")
                st.table(pd.DataFrame(report_data))

                if len(processed_results) == 1:
                    st.download_button(
                        label="📥 Download PDF",
                        data=processed_results[0][0],
                        file_name=f"compressed_{processed_results[0][1]}",
                        mime="application/pdf"
                    )
                else:
                    zip_buffer = BytesIO()
                    with zipfile.ZipFile(zip_buffer, "w") as zf:
                        for data, name in processed_results:
                            zf.writestr(f"compressed_{name}", data)
                    
                    st.download_button(
                        label="📥 Download All (ZIP)",
                        data=zip_buffer.getvalue(),
                        file_name="compressed_files.zip",
                        mime="application/zip"
                    )
