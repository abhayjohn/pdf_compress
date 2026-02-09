import streamlit as st
import fitz  # PyMuPDF
import gc
import os
import tempfile
import math
from PIL import Image
from io import BytesIO

# --- MEMORY PROVISION ---
def purge_system():
    """Wipes RAM to prevent Streamlit 'Connection Reset' errors."""
    gc.collect()
    st.cache_data.clear()

def surgical_compress(input_path, target_mb):
    """Surgically replaces internal images using page-level extraction."""
    doc = fitz.open(input_path)
    orig_mb = os.path.getsize(input_path) / (1024 * 1024)
    
    # Geometric scaling factor: sqrt(Target/Original) ensures 2D size reduction.
    # We use a 0.9 safety multiplier to stay under 20MB.
    scale_factor = math.sqrt(target_mb / orig_mb) * 0.9
    scale_factor = min(1.0, max(0.15, scale_factor)) # Keep between 15% and 100%
    
    # Iterate through every page
    for page in doc:
        image_list = page.get_images(full=True) # Modern way to find images
        
        for img in image_list:
            xref = img[0] # The first element is the cross-reference (xref)
            try:
                base_image = doc.extract_image(xref)
                if not base_image: continue
                
                # Load and Resize (The 50% Scaling Logic)
                pil_img = Image.open(BytesIO(base_image["image"]))
                if pil_img.mode != "RGB":
                    pil_img = pil_img.convert("RGB")
                
                new_size = (int(pil_img.width * scale_factor), int(pil_img.height * scale_factor))
                pil_img = pil_img.resize(new_size, Image.Resampling.LANCZOS)
                
                # Compress with dynamic quality based on file size
                img_buf = BytesIO()
                q_val = 45 if orig_mb > 150 else 65
                pil_img.save(img_buf, format="JPEG", quality=q_val, optimize=True)
                
                # Replace image data surgically
                doc.update_stream(xref, img_buf.getvalue())
                
                pil_img.close()
                img_buf.close()
            except:
                continue

    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as f_out:
        # garbage=4 and clean=True are required to remove old data
        doc.save(f_out.name, garbage=4, deflate=True, clean=True)
        out_path = f_out.name
    
    doc.close()
    return out_path

# --- UI ---
st.set_page_config(page_title="PDF Optimizer", layout="wide")
st.title("🛡️ Stabilized PDF Compressor (<20MB)")

up_file = st.file_uploader("Upload large PDF", type="pdf")

if up_file:
    if st.button("Compress to Under 20MB"):
        # Save to disk to free RAM immediately
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as f_in:
            f_in.write(up_file.getbuffer())
            f_in_path = f_in.name
        
        # PROVISION: Delete from RAM immediately
        del up_file
        purge_system()
        
        with st.spinner("Processing..."):
            try:
                # Target 19.5MB for safety
                final_path = surgical_compress(f_in_path, 19.5)
                
                with open(final_path, "rb") as f:
                    final_data = f.read()
                
                final_mb = len(final_data) / (1024 * 1024)
                st.success(f"Final Size: {final_mb:.2f} MB")
                st.download_button("📥 Download PDF", final_data, "optimized.pdf")
                
                os.remove(f_in_path)
                os.remove(final_path)
                purge_system()
            except Exception as e:
                st.error(f"Error: {e}")
