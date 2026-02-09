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

# Increased limit to 500MB as requested
MAX_FILE_SIZE_MB = 500 

def purge():
    gc.collect()

def fast_compress(input_path, dpi, quality):
    doc = fitz.open(input_path)
    out_doc = fitz.open()
    
    for page in doc:
        zoom = dpi / 72
        mat = fitz.Matrix(zoom, zoom)
        
        # Rendering to pixmap is the most RAM-intensive step
        pix = page.get_pixmap(matrix=mat, colorspace=fitz.csRGB)
        img_data = pix.tobytes("jpg", jpg_quality=quality)
        
        new_page = out_doc.new_page(width=page.rect.width, height=page.rect.height)
        new_page.insert_image(page.rect, stream=img_data)
        
        pix = None # Immediate RAM release

    out_path = tempfile.mktemp(suffix=".pdf")
    out_doc.save(out_path, garbage=4, deflate=True)
    
    doc.close()
    out_doc.close()
    return out_path

# --- UI ---
st.set_page_config(page_title="High-Capacity PDF Compressor", page_icon="⚡")

st.title("⚡ High-Capacity PDF Compressor")
st.info(f"Server configured for files up to {MAX_FILE_SIZE_MB}MB. Processing is queued for stability.")

# Sidebar settings
st.sidebar.header("Compression Settings")
mode = st.sidebar.select_slider(
    "Quality Level",
    options=["Extreme", "Recommended", "High Quality"],
    value="Recommended"
)

settings_map = {
    "Extreme": {"dpi": 60, "quality": 30},
    "Recommended": {"dpi": 75, "quality": 50},
    "High Quality": {"dpi": 110, "quality": 75}
}

up_files = st.file_uploader("Upload PDF files", type="pdf", accept_multiple_files=True)

if up_files:
    total_size_mb = sum(f.size for f in up_files) / (1024 * 1024)
    
    if total_size_mb > MAX_FILE_SIZE_MB:
        st.error(f"❌ Total size ({total_size_mb:.1f}MB) exceeds the {MAX_FILE_SIZE_MB}MB limit.")
    else:
        if st.button(f"Compress {len(up_files)} File(s)"):
            with st.session_state.process_lock:
                processed_results = []
                report_data = []
                
                progress_bar = st.progress(0)
                status_box = st.empty()

                for idx, up_file in enumerate(up_files):
                    status_box.info(f"Processing: **{up_file.name}**")
                    
                    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as f_in:
                        f_in.write(up_file.getbuffer())
                        f_in_path = f_in.name
                    
                    comp_path = None
                    try:
                        comp_path = fast_compress(
                            f_in_path, 
                            settings_map[mode]["dpi"], 
                            settings_map[mode]["quality"]
                        )
                        
                        with open(comp_path, "rb") as f:
                            final_pdf_bytes = f.read()
                        
                        processed_results.append((final_pdf_bytes, up_file.name))
                        
                        orig_s = os.path.getsize(f_in_path) / (1024 * 1024)
                        new_s = len(final_pdf_bytes) / (1024 * 1024)
                        
                        report_data.append({
                            "File Name": up_file.name,
                            "Original": f"{orig_s:.2f} MB",
                            "Compressed": f"{new_s:.2f} MB",
                            "Saved": f"{int((1 - new_s/orig_s)*100)}%"
                        })

                    except Exception as e:
                        st.error(f"Error processing {up_file.name}: {e}")
                    
                    finally:
                        if os.path.exists(f_in_path):
                            os.remove(f_in_path)
                        if comp_path and os.path.exists(comp_path):
                            os.remove(comp_path)
                        purge()
                        progress_bar.progress((idx + 1) / len(up_files))

                status_box.success("✅ Batch Finished!")
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
                        label="📥 Download ZIP",
                        data=zip_buffer.getvalue(),
                        file_name="batch_compressed.zip",
                        mime="application/zip"
                    )
