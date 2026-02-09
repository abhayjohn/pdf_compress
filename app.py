import streamlit as st
import fitz  # PyMuPDF
import gc
import os
import tempfile
from PIL import Image
from io import BytesIO

def purge():
    gc.collect()
    st.cache_data.clear()

def fast_compress(input_path, target_mb):
    doc = fitz.open(input_path)
    out_doc = fitz.open()
    
    orig_mb = os.path.getsize(input_path) / (1024 * 1024)
    # If file is huge, we start with a very low DPI to ensure speed and <20MB
    # We target 72 DPI (Standard screen resolution)
    dpi = 72 
    if orig_mb > 300:
        dpi = 60
    
    progress = st.progress(0, text="Compressing pages...")
    total_pages = len(doc)

    for i, page in enumerate(doc):
        # Convert page to an image (This fixes the 'blank' issue)
        pix = page.get_pixmap(matrix=fitz.Matrix(dpi/72, dpi/72))
        img_data = pix.tobytes("jpg", jpg_quality=50)
        
        # Create new page and insert the compressed image
        new_page = out_doc.new_page(width=page.rect.width, height=page.rect.height)
        new_page.insert_image(page.rect, stream=img_data)
        
        # Memory Provision: Clear the pixmap immediately
        pix = None
        progress.progress((i + 1) / total_pages)
        
        if i % 10 == 0:
            purge()

    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as f_out:
        # Save and optimize
        out_doc.save(f_out.name, garbage=4, deflate=True)
        out_path = f_out.name
    
    doc.close()
    out_doc.close()
    return out_path

# --- UI ---
st.title("⚡ High-Speed PDF Compressor")

up_file = st.file_uploader("Upload PDF", type="pdf")

if up_file:
    if st.button("Compress Now"):
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as f_in:
            f_in.write(up_file.getbuffer())
            f_in_path = f_in.name
        
        # Provision: Delete upload from RAM
        del up_file
        purge()
        
        try:
            final_path = fast_compress(f_in_path, 20)
            
            with open(final_path, "rb") as f:
                final_bytes = f.read()
            
            st.success(f"Done! Size: {len(final_bytes)/(1024*1024):.2f} MB")
            st.download_button("📥 Download PDF", final_bytes, "compressed.pdf")
            
            os.remove(f_in_path)
            os.remove(final_path)
            purge()
        except Exception as e:
            st.error(f"Error: {e}")
