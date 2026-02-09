import streamlit as st
import fitz  # PyMuPDF
import gc
import os
import tempfile
import math
from PIL import Image
from io import BytesIO

# --- SYSTEM UTILITIES ---
def purge_memory():
    """Clears RAM to prevent Streamlit crashes."""
    gc.collect()
    st.cache_data.clear()

def get_size_at_dpi(input_path, dpi, use_grayscale, sample_pages=5):
    """Probes the file to see how many MBs it generates at a specific DPI."""
    doc = fitz.open(input_path)
    total_pages = len(doc)
    sample_count = min(sample_pages, total_pages)
    
    sample_doc = fitz.open()
    cs = fitz.csGRAY if use_grayscale else fitz.csRGB
    
    for i in range(sample_count):
        page = doc[i]
        pix = page.get_pixmap(matrix=fitz.Matrix(dpi/72, dpi/72), colorspace=cs)
        img_data = pix.tobytes("jpg", jpg_quality=75)
        new_page = sample_doc.new_page(width=page.rect.width, height=page.rect.height)
        new_page.insert_image(page.rect, stream=img_data)
    
    sample_buffer = BytesIO()
    sample_doc.save(sample_buffer, garbage=3)
    # Calculate projected total size
    projected_mb = (sample_buffer.getbuffer().nbytes / sample_count) * total_pages / (1024 * 1024)
    
    sample_doc.close()
    doc.close()
    return projected_mb

def process_final_pdf(input_path, dpi, use_grayscale):
    """Final output generation."""
    doc = fitz.open(input_path)
    out_doc = fitz.open()
    cs = fitz.csGRAY if use_grayscale else fitz.csRGB
    
    for page in doc:
        mat = fitz.Matrix(dpi/72, dpi/72)
        pix = page.get_pixmap(matrix=mat, colorspace=cs)
        img_data = pix.tobytes("jpg", jpg_quality=80) # Higher quality for the final calculated DPI
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
st.set_page_config(page_title="Ratio Optimizer", layout="wide")
st.title("🎯 Ratio-Based PDF Optimizer")

tab1, tab2 = st.tabs(["🗜️ Compressor", "🖼️ Images to PDF"])

with tab1:
    up_pdf = st.file_uploader("Upload PDF (Max 500MB)", type="pdf")
    use_gray = st.checkbox("Grayscale Mode", value=False)

    if up_pdf:
        if st.button("Compress Using Ratio Calculation"):
            # 1. Save to disk and clear RAM
            with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as f_in:
                f_in.write(up_pdf.getbuffer())
                f_in_path = f_in.name
            
            del up_pdf
            purge_memory()

            try:
                # 2. The Probing Pass (at 100 DPI)
                with st.spinner("Probing file at 100 DPI..."):
                    current_mb = get_size_at_dpi(f_in_path, 100, use_gray)
                
                # 3. Calculate Ratio
                # Formula: New DPI = 100 * sqrt(19.5 / current_mb)
                # We use 19.5 to stay safely under the 20MB limit
                ratio = math.sqrt(19.5 / current_mb)
                calculated_dpi = int(100 * ratio)
                
                # Safety Cap: Don't let DPI go too high or too low
                calculated_dpi = max(30, min(calculated_dpi, 250))
                
                st.info(f"Probed Size: {current_mb:.2f}MB. Calculated optimal DPI: {calculated_dpi}")

                # 4. Final Pass
                with st.spinner(f"Finalizing at {calculated_dpi} DPI..."):
                    final_path = process_final_pdf(f_in_path, calculated_dpi, use_gray)
                    
                    with open(final_path, "rb") as f:
                        final_data = f.read()
                    
                    actual_size = len(final_data)/(1024*1024)
                    st.success(f"Final Size: {actual_size:.2f} MB")
                    st.download_button("📥 Download PDF", final_data, "optimized.pdf")
                    
                    os.remove(final_path)

            except Exception as e:
                st.error(f"Error: {e}")
            finally:
                if os.path.exists(f_in_path):
                    os.remove(f_in_path)
                purge_memory()

with tab2:
    # Stable Image-to-PDF Converter
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
