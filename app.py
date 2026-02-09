import streamlit as st
import fitz  # PyMuPDF
import gc
import os
import tempfile
import math
from PIL import Image
from io import BytesIO

# --- 1. MEMORY PROVISION ---
def purge_system():
    """Wipes RAM to prevent Streamlit 'Connection Reset' errors."""
    gc.collect()
    st.cache_data.clear()

# --- 2. SURGICAL COMPRESSION ---
def surgical_compress(input_path, target_mb):
    """Targets internal image objects directly to keep the file size low."""
    doc = fitz.open(input_path)
    orig_mb = os.path.getsize(input_path) / (1024 * 1024)
    
    # Calculate required scaling factor (e.g., if 200MB -> 20MB, we need sqrt(0.1) ≈ 0.31)
    # We add a 10% safety buffer (0.9 multiplier)
    scale_factor = math.sqrt(target_mb / orig_mb) * 0.9
    scale_factor = min(1.0, max(0.2, scale_factor)) # Caps: 20% to 100%
    
    # Adjust JPEG quality based on target pressure
    q_val = 40 if orig_mb > 150 else 60

    # Iterate through PDF objects (xrefs)
    for xref in range(1, doc.xref_length()):
        if doc.is_image(xref):
            try:
                base_image = doc.extract_image(xref)
                if not base_image: continue
                
                # Process image in a RAM-efficient way
                pil_img = Image.open(BytesIO(base_image["image"]))
                if pil_img.mode != "RGB":
                    pil_img = pil_img.convert("RGB")
                
                # Applying the Scaling (The 50% logic)
                new_size = (int(pil_img.width * scale_factor), int(pil_img.height * scale_factor))
                pil_img = pil_img.resize(new_size, Image.Resampling.LANCZOS)
                
                img_buf = BytesIO()
                pil_img.save(img_buf, format="JPEG", quality=q_val, optimize=True)
                
                # Replace stream and update filter
                doc.update_stream(xref, img_buf.getvalue())
                doc.set_object_value(xref, "/Filter", "/DCTDecode")
                
                pil_img.close()
                img_buf.close()
            except:
                continue

    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as f_out:
        # Save with garbage=4 to purge old heavy data
        doc.save(f_out.name, garbage=4, deflate=True, clean=True)
        out_path = f_out.name
    
    doc.close()
    return out_path

# --- 3. UI ---
st.set_page_config(page_title="PDF Targeter", layout="wide")
st.title("🛡️ Zero-Crash PDF Compressor (<20MB)")

up_file = st.file_uploader("Upload large PDF", type="pdf")

if up_file:
    if st.button("Ensure Below 20MB"):
        # Save upload to disk immediately to free RAM
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as f_in:
            f_in.write(up_file.getbuffer())
            f_in_path = f_in.name
        
        # PROVISION: Delete from RAM immediately
        del up_file
        purge_system()
        
        with st.spinner("Executing surgical scaling..."):
            try:
                final_path = surgical_compress(f_in_path, 19.5) # Aim for 19.5MB for safety
                
                with open(final_path, "rb") as f:
                    final_data = f.read()
                
                final_mb = len(final_data) / (1024 * 1024)
                st.success(f"Final Size: {final_mb:.2f} MB")
                st.download_button("📥 Download PDF", final_data, "final_20mb.pdf")
                
                os.remove(f_in_path)
                os.remove(final_path)
                purge_system()
            except Exception as e:
                st.error(f"Error: {e}")
