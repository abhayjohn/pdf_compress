import streamlit as st
import fitz  # PyMuPDF
import gc
import os
import tempfile
from PIL import Image
from io import BytesIO

# --- SYSTEM UTILITIES ---
def purge_system():
    """Wipes RAM and Streamlit's internal cache to prevent crashes."""
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
st.set_page_config(page_title="PDF Convergent Tool", layout="wide")
st.title("🎯 Convergent 18-20MB Compressor")
st.markdown("Uses damped feedback to prevent DPI jumping and hit the target precisely.")

tab1, tab2 = st.tabs(["🗜️ Polling Compressor", "🖼️ Images to PDF"])

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

            # Iteration Setup
            current_dpi = 100
            current_quality = 75
            attempts = 0
            max_attempts = 10 
            
            status_placeholder = st.empty()
            history = []
            
            while attempts < max_attempts:
                attempts += 1
                status_placeholder.info(f"Attempt {attempts}: Testing {current_dpi} DPI...")
                
                temp_path = process_pdf(f_in_path, current_dpi, current_quality, use_gray)
                actual_mb = os.path.getsize(temp_path) / (1024 * 1024)
                history.append(f"DPI {current_dpi}: {actual_mb:.2f} MB")
                
                # Success Condition
                if 18.0 <= actual_mb <= 20.0:
                    status_placeholder.success(f"Target Reached! Final Size: {actual_mb:.2f} MB")
                    with open(temp_path, "rb") as f:
                        final_data = f.read()
                    os.remove(temp_path)
                    st.download_button("📥 Download Final PDF", final_data, "final_20mb.pdf")
                    break
                
                # Convergent Logic: Damped Square Root Ratio
                # Instead of jumping fully to the new ratio, we move only 70% of the way (Damping)
                target_mb = 19.2 # Aim for the middle of the 18-20 range
                ratio = (target_mb / actual_mb) ** 0.5
                
                # Apply Damping (mix of old DPI and suggested DPI)
                suggested_dpi = int(current_dpi * ratio)
                current_dpi = int((current_dpi * 0.3) + (suggested_dpi * 0.7))
                
                # Safety Caps
                current_dpi = max(30, min(current_dpi, 250))

                os.remove(temp_path)
                purge_system() 

            st.write("📈 Compression History:", history)
            
            # Final disk cleanup
            if os.path.exists(f_in_path):
                os.remove(f_in_path)
            purge_system()

with tab2:
    imgs = st.file_uploader("Select Images", type=["jpg", "png"], accept_multiple_files=True, key="img_uploader")
    if imgs and st.button("Convert & Purge"):
        pdf = fitz.open()
        for img_f in imgs:
            img_obj = Image.open(BytesIO(img_f.read())).convert("RGB")
            buf = BytesIO()
            img_obj.save(buf, format="JPEG", quality=80)
            p = pdf.new_page(width=img_obj.size[0], height=img_obj.size[1])
            p.insert_image(p.rect, stream=buf.getvalue())
            img_obj.close()
        st.download_button("Download PDF", pdf.tobytes(), "images.pdf")
        del imgs
        purge_system()
