import streamlit as st
import fitz  # PyMuPDF
import gc
import os
import tempfile
from PIL import Image
from io import BytesIO

# --- SYSTEM UTILITIES ---
def purge_system():
    """Forces the system to reclaim unused RAM immediately."""
    gc.collect()
    st.cache_data.clear()
    st.cache_resource.clear()

def process_pdf(input_path, dpi, quality, use_grayscale):
    """Generates PDF and returns the disk path."""
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
st.set_page_config(page_title="PDF Precision Optimizer", layout="wide")
st.title("🎯 Precision 20MB Optimizer")
st.markdown("This app iteratively tunes DPI and quality to get as close to **19.99MB** as possible.")

tab1, tab2 = st.tabs(["🗜️ High-Precision Compressor", "🖼️ Images to PDF"])

with tab1:
    up_pdf = st.file_uploader("Upload PDF (Max 500MB)", type="pdf", key="pdf_uploader")
    use_gray = st.checkbox("Grayscale Mode", value=True)

    if up_pdf:
        if st.button("Start Precision Compression"):
            # Step 1: Offload from RAM to Disk immediately
            with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as f_in:
                f_in.write(up_pdf.getbuffer())
                f_in_path = f_in.name
            
            # Step 2: Clear the uploaded file from RAM immediately
            del up_pdf 
            purge_system()

            # High-Precision Iteration Setup
            current_dpi = 100
            current_quality = 80
            attempts = 0
            max_attempts = 12 # Increased for tighter convergence
            
            status_placeholder = st.empty()
            history = []
            best_data = None
            best_size = 0
            
            while attempts < max_attempts:
                attempts += 1
                status_placeholder.info(f"Attempt {attempts}: Testing {current_dpi} DPI...")
                
                temp_path = process_pdf(f_in_path, current_dpi, current_quality, use_gray)
                actual_mb = os.path.getsize(temp_path) / (1024 * 1024)
                history.append(f"DPI {current_dpi}: {actual_mb:.2f} MB")
                
                # Update "Best version so far" if it's under 20MB
                if actual_mb <= 20.0 and actual_mb > best_size:
                    with open(temp_path, "rb") as f:
                        best_data = f.read()
                    best_size = actual_mb

                # Stop if we hit the "Goldilocks" spot (19.8MB - 20.0MB)
                if 19.8 <= actual_mb <= 20.0:
                    status_placeholder.success(f"Precision Target Hit! Final Size: {actual_mb:.2f} MB")
                    break
                
                # Feedback logic: Aiming for 19.9MB
                target_mb = 19.95
                
                # If we are over, use a stronger damping to avoid huge jumps
                if actual_mb > 20.0:
                    ratio = (target_mb / actual_mb) ** 0.5
                    suggested_dpi = int(current_dpi * ratio)
                    current_dpi = int((current_dpi * 0.4) + (suggested_dpi * 0.6))
                # If we are under, push the DPI or Quality up
                else:
                    ratio = (target_mb / actual_mb) ** 0.5
                    suggested_dpi = int(current_dpi * ratio)
                    current_dpi = int((current_dpi * 0.2) + (suggested_dpi * 0.8))
                    current_quality = min(95, current_quality + 2)

                # Prevent DPI from becoming invalid
                current_dpi = max(30, min(current_dpi, 300))

                os.remove(temp_path)
                purge_system() 

            if best_data:
                st.write(f"📈 Final Optimized Size: {best_size:.2f} MB")
                st.download_button("📥 Download Final PDF", best_data, "final_20mb.pdf")
            else:
                st.error("Could not generate a version under 20MB. Try Grayscale mode.")
            
            st.write("Compression History:", history)
            
            if os.path.exists(f_in_path):
                os.remove(f_in_path)
            purge_system()

with tab2:
    # Stable Image to PDF Converter
    imgs = st.file_uploader("Select Images", type=["jpg", "png"], accept_multiple_files=True, key="img_uploader")
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
        del imgs
        purge_system()
