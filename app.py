import streamlit as st
import fitz  # PyMuPDF
import gc
import os
import tempfile
from PIL import Image
from io import BytesIO

# --- SYSTEM UTILITIES ---
def purge_memory():
    gc.collect()
    st.cache_data.clear()

def process_pdf(input_path, dpi, quality, use_grayscale):
    """Core compression function."""
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

# --- UI SETUP ---
st.set_page_config(page_title="20MB Precision Tool", layout="wide")
st.title("🎯 Auto-Iterative 20MB Targeter")

up_pdf = st.file_uploader("Upload PDF (Max 500MB)", type="pdf")
use_gray = st.checkbox("Force Grayscale (Easier to hit 20MB with high clarity)")

if up_pdf:
    if st.button("Start High-Precision Compression"):
        # Save upload to disk
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as f_in:
            f_in.write(up_pdf.getbuffer())
            f_in_path = f_in.name
        
        del up_pdf
        purge_memory()

        # START RECURSIVE OPTIMIZATION
        # Starting guesses
        current_dpi = 100
        current_quality = 70
        attempts = 0
        max_attempts = 5
        final_pdf_data = None
        
        status_box = st.empty()
        
        while attempts < max_attempts:
            attempts += 1
            status_box.info(f"Attempt {attempts}: Testing {current_dpi} DPI...")
            
            # Process the file
            temp_result_path = process_pdf(f_in_path, current_dpi, current_quality, use_gray)
            file_size_mb = os.path.getsize(temp_result_path) / (1024 * 1024)
            
            # Check if we are in the "Perfect Zone" (18.5MB - 19.9MB)
            if 18.5 <= file_size_mb <= 20.0:
                status_box.success(f"Perfect hit! Final Size: {file_size_mb:.2f} MB")
                with open(temp_result_path, "rb") as f:
                    final_pdf_data = f.read()
                os.remove(temp_result_path)
                break
            
            # If too large, decrease DPI
            elif file_size_mb > 20.0:
                status_box.warning(f"Too large ({file_size_mb:.2f} MB). Reducing DPI...")
                # Reduce DPI proportional to how much we missed
                reduction_factor = 20.0 / file_size_mb
                current_dpi = int(current_dpi * reduction_factor * 0.95)
                os.remove(temp_result_path)
            
            # If much too small (under 18.5MB), increase quality/DPI
            else:
                status_box.info(f"Too small ({file_size_mb:.2f} MB). Increasing quality...")
                increase_factor = 19.5 / file_size_mb
                current_dpi = int(current_dpi * (increase_factor ** 0.5))
                current_quality = min(95, int(current_quality * 1.1))
                # If we've already done 3+ attempts, we'll take the 18MB+ version
                if file_size_mb > 17.5:
                    with open(temp_result_path, "rb") as f:
                        final_pdf_data = f.read()
                    os.remove(temp_result_path)
                    break
                os.remove(temp_result_path)
            
            purge_memory()

        if final_pdf_data:
            st.download_button("📥 Download Final Precision PDF", final_pdf_data, "precision_20mb.pdf")
        
        if os.path.exists(f_in_path):
            os.remove(f_in_path)
        purge_memory()
