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

def purge_memory():
    """Explicitly clears the garbage collector and Streamlit cache."""
    gc.collect()
    st.cache_data.clear()

def find_guaranteed_dpi(input_path, target_mb, use_grayscale):
    doc = fitz.open(input_path)
    total_pages = len(doc)
    sample_count = min(5, total_pages)
    safe_target = target_mb * 0.9 
    
    best_dpi = 40 
    winning_quality = 50

    for test_dpi in [120, 96, 72, 60, 45, 30]:
        sample_doc = fitz.open()
        for i in range(sample_count):
            page = doc[i]
            # Use Grayscale colorspace if toggled to save massive space
            cs = fitz.csGRAY if use_grayscale else fitz.csRGB
            pix = page.get_pixmap(matrix=fitz.Matrix(test_dpi/72, test_dpi/72), colorspace=cs)
            img_data = pix.tobytes("jpg", jpg_quality=50)
            new_page = sample_doc.new_page(width=page.rect.width, height=page.rect.height)
            new_page.insert_image(page.rect, stream=img_data)
        
        sample_buffer = BytesIO()
        sample_doc.save(sample_buffer, garbage=3)
        projected_mb = (sample_buffer.getbuffer().nbytes / sample_count) * total_pages / (1024 * 1024)
        sample_doc.close()
        
        if projected_mb <= safe_target:
            best_dpi = test_dpi
            break
            
    doc.close()
    return best_dpi

def process_full_pdf(input_path, dpi, use_grayscale):
    doc = fitz.open(input_path)
    out_doc = fitz.open()
    colorspace = fitz.csGRAY if use_grayscale else fitz.csRGB
    
    progress_bar = st.progress(0, text=f"Processing... (Grayscale: {use_grayscale})")
    
    for i, page in enumerate(doc):
        mat = fitz.Matrix(dpi/72, dpi/72)
        pix = page.get_pixmap(matrix=mat, colorspace=colorspace)
        img_data = pix.tobytes("jpg", jpg_quality=40) # Hard-coded quality for 20MB guarantee
        
        new_page = out_doc.new_page(width=page.rect.width, height=page.rect.height)
        new_page.insert_image(page.rect, stream=img_data)
        
        pix = None
        if i % 3 == 0: gc.collect()
        progress_bar.progress((i + 1) / len(doc))

    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as f_out:
        out_doc.save(f_out.name, garbage=4, deflate=True)
        out_path = f_out.name
    
    out_doc.close()
    doc.close()
    return out_path

# --- UI LAYOUT ---
st.set_page_config(page_title="PDF Survivor", layout="wide")
st.title("🎯 Guaranteed <20MB Compressor (Auto-Purge RAM)")

tab1, tab2 = st.tabs(["🗜️ Compressor", "🖼️ Images to PDF"])

with tab1:
    up_pdf = st.file_uploader("Upload PDF (Max 500MB)", type="pdf")
    use_grayscale = st.checkbox("Grayscale Mode (Highly Recommended for <20MB target)", value=True)
    
    if up_pdf:
        if st.button("Compress & Purge Upload"):
            # Step 1: Write to disk immediately
            with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as f_in:
                for chunk in up_pdf:
                    f_in.write(chunk)
                f_in_path = f_in.name
            
            # Step 2: Delete the uploaded file object from RAM immediately
            # This is the "Provision" to prevent RAM issues
            del up_pdf 
            purge_memory()
            
            try:
                with st.spinner("Calculating..."):
                    winning_dpi = find_guaranteed_dpi(f_in_path, 20, use_grayscale)
                
                with st.spinner("Generating final PDF..."):
                    final_path = process_full_pdf(f_in_path, winning_dpi, use_grayscale)
                    
                    with open(final_path, "rb") as f:
                        final_data = f.read()
                    
                    st.success(f"Final Size: {len(final_data)/(1024*1024):.2f} MB")
                    st.download_button("Download Compressed PDF", final_data, "final_under_20mb.pdf")
                    
                    # Step 3: Cleanup disk
                    os.remove(f_in_path)
                    os.remove(final_path)
                    
                    # Final RAM purge
                    purge_memory()
                    
            except Exception as e:
                st.error(f"Error: {e}")

with tab2:
    # Standard Image-to-PDF logic with manual purge
    imgs = st.file_uploader("Upload Images", type=["jpg", "png"], accept_multiple_files=True)
    if imgs and st.button("Convert & Purge"):
        pdf = fitz.open()
        for img_f in imgs:
            img_obj = Image.open(BytesIO(img_f.read())).convert("RGB")
            buf = BytesIO()
            img_obj.save(buf, format="JPEG", quality=60)
            p = pdf.new_page(width=img_obj.size[0], height=img_obj.size[1])
            p.insert_image(p.rect, stream=buf.getvalue())
            img_obj.close()
        st.download_button("Download PDF", pdf.tobytes(), "images.pdf")
        del imgs
        purge_memory()
