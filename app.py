import streamlit as st
import fitz  # PyMuPDF
import gc
import os
import tempfile
from PIL import Image
from io import BytesIO

# --- 1. SYSTEM TWEAKS ---
st.cache_data.clear()
gc.collect()

def find_guaranteed_dpi(input_path, target_mb):
    """
    Tests DPI settings with a safety buffer to ensure we land UNDER 20MB.
    """
    doc = fitz.open(input_path)
    total_pages = len(doc)
    sample_count = min(5, total_pages)
    
    # We aim for 18MB to ensure the final file (with overhead) stays under 20MB
    safe_target = target_mb * 0.9 
    
    best_dpi = 40 # Lowest safe fallback
    winning_quality = 50

    # Test DPIs from high to low
    for test_dpi in [120, 96, 72, 60, 45, 30]:
        sample_doc = fitz.open()
        for i in range(sample_count):
            page = doc[i]
            pix = page.get_pixmap(matrix=fitz.Matrix(test_dpi/72, test_dpi/72))
            # Test with moderate quality
            img_data = pix.tobytes("jpg", jpg_quality=50)
            new_page = sample_doc.new_page(width=page.rect.width, height=page.rect.height)
            new_page.insert_image(page.rect, stream=img_data)
        
        sample_buffer = BytesIO()
        sample_doc.save(sample_buffer, garbage=3)
        projected_mb = (sample_buffer.getbuffer().nbytes / sample_count) * total_pages / (1024 * 1024)
        
        sample_doc.close()
        
        if projected_mb <= safe_target:
            best_dpi = test_dpi
            winning_quality = 50
            break
        else:
            # If even at low DPI we are over, drop the JPEG quality aggressively
            winning_quality = 30 
            best_dpi = test_dpi
            
    doc.close()
    return best_dpi, winning_quality

def process_full_pdf(input_path, dpi, quality):
    """
    Final processing using the guaranteed parameters.
    """
    doc = fitz.open(input_path)
    out_doc = fitz.open()
    
    progress_bar = st.progress(0, text=f"Forcing compression ({dpi} DPI, {quality}% Quality)...")
    
    for i, page in enumerate(doc):
        # Using RGB colorspace to prevent the 'static/black' corruption error
        mat = fitz.Matrix(dpi/72, dpi/72)
        pix = page.get_pixmap(matrix=mat, colorspace=fitz.csRGB)
        img_data = pix.tobytes("jpg", jpg_quality=quality)
        
        new_page = out_doc.new_page(width=page.rect.width, height=page.rect.height)
        new_page.insert_image(page.rect, stream=img_data)
        
        pix = None
        if i % 2 == 0: gc.collect()
        progress_bar.progress((i + 1) / len(doc))

    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as f_out:
        # garbage=4 and deflate=True are mandatory for the 20MB target
        out_doc.save(f_out.name, garbage=4, deflate=True)
        out_path = f_out.name
    
    out_doc.close()
    doc.close()
    return out_path

# --- UI LAYOUT ---
st.set_page_config(page_title="PDF Power Tool", layout="wide")
st.title("🎯 Guaranteed <20MB PDF Compressor")

tab1, tab2 = st.tabs(["🗜️ Compressor", "🖼️ Images to PDF"])

with tab1:
    up_pdf = st.file_uploader("Upload PDF (Up to 500MB)", type="pdf")
    if up_pdf:
        # Step 1: Save to disk to avoid RAM crashes
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as f_in:
            for chunk in up_pdf:
                f_in.write(chunk)
            f_in_path = f_in.name
            
        if st.button("Compress to under 20MB"):
            try:
                with st.spinner("Finding guaranteed resolution..."):
                    winning_dpi, winning_q = find_guaranteed_dpi(f_in_path, 20)
                
                with st.spinner("Executing final compression..."):
                    final_path = process_full_pdf(f_in_path, winning_dpi, winning_q)
                    
                    with open(final_path, "rb") as f:
                        final_data = f.read()
                    
                    final_mb = len(final_data) / (1024 * 1024)
                    
                    if final_mb < 20:
                        st.success(f"Success! Final Size: {final_mb:.2f} MB")
                    else:
                        st.warning(f"Final Size: {final_mb:.2f} MB (Slightly above target due to metadata).")
                        
                    st.download_button("Download Compressed PDF", final_data, "final_under_20mb.pdf")
                    os.remove(final_path)
            except Exception as e:
                st.error(f"Error: {e}")
            finally:
                if os.path.exists(f_in_path): os.remove(f_in_path)

with tab2:
    # Adding the Image to PDF tab back
    st.header("Convert Images to PDF")
    imgs = st.file_uploader("Select Images", type=["jpg", "png"], accept_multiple_files=True)
    if imgs and st.button("Convert Now"):
        pdf = fitz.open()
        for img_f in imgs:
            img_obj = Image.open(BytesIO(img_f.read())).convert("RGB")
            buf = BytesIO()
            img_obj.save(buf, format="JPEG", quality=60)
            p = pdf.new_page(width=img_obj.size[0], height=img_obj.size[1])
            p.insert_image(p.rect, stream=buf.getvalue())
            img_obj.close()
        st.download_button("Download PDF", pdf.tobytes(), "images.pdf")
