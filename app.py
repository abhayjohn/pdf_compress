import streamlit as st
import fitz  # PyMuPDF
import gc
import os
import tempfile
from PIL import Image
from io import BytesIO

# --- 1. MEMORY MANAGEMENT ---
def purge_memory():
    """Forces the system to reclaim unused RAM immediately."""
    gc.collect()
    st.cache_data.clear()

def process_pdf(input_path, dpi, quality, use_grayscale):
    """Generates a full PDF and returns the path to the file on disk."""
    doc = fitz.open(input_path)
    out_doc = fitz.open()
    cs = fitz.csGRAY if use_grayscale else fitz.csRGB
    
    for page in doc:
        mat = fitz.Matrix(dpi/72, dpi/72)
        pix = page.get_pixmap(matrix=mat, colorspace=cs)
        img_data = pix.tobytes("jpg", jpg_quality=quality)
        
        new_page = out_doc.new_page(width=page.rect.width, height=page.rect.height)
        new_page.insert_image(page.rect, stream=img_data)
        pix = None
        
    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as f_out:
        out_doc.save(f_out.name, garbage=4, deflate=True)
        out_path = f_out.name
    
    out_doc.close()
    doc.close()
    return out_path

# --- 2. UI SETUP ---
st.set_page_config(page_title="PDF Survivor", layout="wide")
st.title("🎯 Auto-Iterative 20MB Compressor")
st.markdown("This app will repeatedly re-try compression until the file is between 18MB and 20MB.")

tab1, tab2 = st.tabs(["🗜️ Auto-Polling Compressor", "🖼️ Images to PDF"])

with tab1:
    up_pdf = st.file_uploader("Upload PDF (Max 500MB)", type="pdf")
    use_gray = st.checkbox("Use Grayscale (Recommended for 20MB limit)", value=True)

    if up_pdf:
        if st.button("Start Iterative Compression"):
            # Save upload to disk and immediately free RAM
            with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as f_in:
                f_in.write(up_pdf.getbuffer())
                f_in_path = f_in.name
            
            del up_pdf # Provision to delete uploaded file from RAM
            purge_memory()

            # Iteration Variables
            current_dpi = 100
            current_quality = 70
            attempts = 0
            max_attempts = 5
            final_pdf_data = None
            
            status_placeholder = st.empty()
            
            while attempts < max_attempts:
                attempts += 1
                status_placeholder.info(f"Attempt {attempts}: Testing {current_dpi} DPI...")
                
                # Perform full compression
                temp_path = process_pdf(f_in_path, current_dpi, current_quality, use_gray)
                actual_mb = os.path.getsize(temp_path) / (1024 * 1024)
                
                # Check results
                if 17.5 <= actual_mb <= 20.0:
                    status_placeholder.success(f"Target Hit! Final Size: {actual_mb:.2f} MB")
                    with open(temp_path, "rb") as f:
                        final_pdf_data = f.read()
                    os.remove(temp_path)
                    break
                
                # Adjust for next attempt
                elif actual_mb > 20.0:
                    status_placeholder.warning(f"Result too large ({actual_mb:.2f} MB). Reducing DPI...")
                    # Geometric reduction
                    current_dpi = int(current_dpi * (20.0 / actual_mb) * 0.9)
                else:
                    status_placeholder.info(f"Result too small ({actual_mb:.2f} MB). Increasing DPI/Quality...")
                    # Increase DPI to fill the 20MB space
                    current_dpi = int(current_dpi * (19.0 / actual_mb) ** 0.5)
                    current_quality = min(95, current_quality + 10)

                os.remove(temp_path)
                purge_memory()
                
                if attempts == max_attempts:
                    st.error("Could not reach exactly 20MB after 5 tries, but here is the closest version.")

            if final_pdf_data:
                st.download_button("📥 Download Final PDF", final_pdf_data, "final_20mb.pdf")
            
            if os.path.exists(f_in_path):
                os.remove(f_in_path)
            purge_memory()

with tab2:
    # Stable Image to PDF Converter
    imgs = st.file_uploader("Select Images", type=["jpg", "png"], accept_multiple_files=True)
    if imgs and st.button("Convert & Purge"):
        pdf = fitz.open()
        for img_f in imgs:
            img_obj = Image.open(BytesIO(img_f.read())).convert("RGB")
            buf = BytesIO()
            img_obj.save(buf, format="JPEG", quality=85)
            p = pdf.new_page(width=img_obj.size[0], height=img_obj.size[1])
            p.insert_image(p.rect, stream=buf.getvalue())
            img_obj.close()
        st.download_button("Download Image PDF", pdf.tobytes(), "images.pdf")
        purge_memory()
