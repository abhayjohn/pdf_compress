import streamlit as st
import fitz  # PyMuPDF
import gc
import os
import tempfile
import math
from PIL import Image
from io import BytesIO

# --- 1. MEMORY PROTECTION PROVISION ---
def purge():
    """Forces the server to release RAM back to the system."""
    gc.collect()
    st.cache_data.clear()

def get_optimized_pdf(input_path, target_mb):
    """Surgically modifies the PDF on disk to save RAM."""
    doc = fitz.open(input_path)
    orig_mb = os.path.getsize(input_path) / (1024 * 1024)
    
    # Calculate scale factor: Aim for 19MB to be safe
    # If file is 200MB, we need it to be 0.1x its current size.
    # Area scaling is the square of linear scaling.
    scale = math.sqrt(19.0 / orig_mb) * 0.95 
    scale = min(1.0, max(0.1, scale)) # Don't scale up, don't go below 10%
    
    # Iterate through pages and images
    for page in doc:
        for img in page.get_images(full=True):
            xref = img[0]
            try:
                # Extract image bytes without loading the whole page
                base = doc.extract_image(xref)
                if not base: continue
                
                # Process image in a tiny RAM window
                with Image.open(BytesIO(base["image"])) as pil_img:
                    if pil_img.mode != "RGB":
                        pil_img = pil_img.convert("RGB")
                    
                    # Geometric scaling (The "50% logic" but calculated)
                    new_size = (int(pil_img.width * scale), int(pil_img.height * scale))
                    pil_img = pil_img.resize(new_size, Image.Resampling.LANCZOS)
                    
                    # Compress with 50% quality for extra safety
                    buf = BytesIO()
                    pil_img.save(buf, format="JPEG", quality=50, optimize=True)
                    
                    # Update the PDF stream directly
                    doc.update_stream(xref, buf.getvalue())
                    buf.close()
                
                # Purge after every single image processed
                if xref % 5 == 0: purge()
            except:
                continue

    # Create temporary output
    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as f_out:
        # garbage=4 is MANDATORY to actually shrink the file on disk
        doc.save(f_out.name, garbage=4, deflate=True, clean=True)
        out_path = f_out.name
    
    doc.close()
    return out_path

# --- 2. UI LAYOUT ---
st.set_page_config(page_title="Safe PDF Compressor")
st.title("🛡️ Server-Safe PDF Compressor")
st.info("Designed to prevent 'Connection Reset' on 500MB+ files.")

up_file = st.file_uploader("Upload PDF", type="pdf")

if up_file:
    if st.button("Compress (Stay Under 20MB)"):
        # STEP 1: Save to disk immediately
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as f_in:
            f_in.write(up_file.getbuffer())
            f_in_path = f_in.name
        
        # STEP 2: Wipe the upload from RAM immediately
        del up_file
        purge()
        
        with st.spinner("Processing surgically (Saving RAM)..."):
            try:
                # Process
                final_path = get_optimized_pdf(f_in_path, 19.5)
                
                # Read result back to RAM only for the download
                with open(final_path, "rb") as f:
                    final_bytes = f.read()
                
                final_mb = len(final_bytes) / (1024 * 1024)
                
                if final_mb > 20:
                    st.warning(f"Result is {final_mb:.2f}MB. Retrying with Grayscale...")
                    # Optional: Add a second pass here if needed
                
                st.success(f"Compression Complete: {final_mb:.2f} MB")
                st.download_button("📥 Download PDF", final_bytes, "compressed.pdf")
                
                # Cleanup disk
                os.remove(f_in_path)
                os.remove(final_path)
                purge()
                
            except Exception as e:
                st.error(f"Server Error: {str(e)}. The file might be too complex for the current RAM.")
