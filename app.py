import streamlit as st
import fitz  # PyMuPDF
import gc
import os
import tempfile
import math
from PIL import Image
from io import BytesIO

# --- MEMORY PROTECTION ---
def purge():
    gc.collect()
    st.cache_data.clear()

def get_optimized_pdf(input_path, target_mb):
    doc = fitz.open(input_path)
    # Create a new blank PDF to hold the compressed pages
    out_doc = fitz.open() 
    
    orig_mb = os.path.getsize(input_path) / (1024 * 1024)
    
    # Calculate scale factor to hit ~19MB
    scale = math.sqrt(19.0 / orig_mb) * 0.9
    scale = min(1.0, max(0.1, scale)) 

    for page in doc:
        # Create a new page with the same dimensions
        new_page = out_doc.new_page(width=page.rect.width, height=page.rect.height)
        
        # Get all images on the page
        img_info = page.get_images(full=True)
        
        if not img_info:
            # If no images, just show the original page content (text/vectors)
            new_page.show_pdf_page(new_page.rect, doc, page.number)
        else:
            # Re-draw the page content (text) first
            new_page.show_pdf_page(new_page.rect, doc, page.number)
            
            for img in img_info:
                xref = img[0]
                # Get the location of the image on the original page
                img_rects = page.get_image_rects(xref)
                
                try:
                    base = doc.extract_image(xref)
                    if not base: continue
                    
                    with Image.open(BytesIO(base["image"])) as pil_img:
                        if pil_img.mode != "RGB":
                            pil_img = pil_img.convert("RGB")
                        
                        # Apply scaling
                        new_size = (int(pil_img.width * scale), int(pil_img.height * scale))
                        pil_img = pil_img.resize(new_size, Image.Resampling.LANCZOS)
                        
                        buf = BytesIO()
                        pil_img.save(buf, format="JPEG", quality=40)
                        
                        # Overwrite the image area with the new compressed version
                        for r in img_rects:
                            new_page.insert_image(r, stream=buf.getvalue())
                        buf.close()
                except:
                    continue
        
        # Periodic RAM cleanup
        if page.number % 5 == 0: purge()

    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as f_out:
        # garbage=4, deflate=True is the key to massive reduction
        out_doc.save(f_out.name, garbage=4, deflate=True)
        out_path = f_out.name
    
    doc.close()
    out_doc.close()
    return out_path

# --- UI ---
st.set_page_config(page_title="Safe PDF Compressor")
st.title("🛡️ Fixed Server-Safe Compressor")

up_file = st.file_uploader("Upload PDF", type="pdf")

if up_file:
    if st.button("Compress (Target Under 20MB)"):
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as f_in:
            f_in.write(up_file.getbuffer())
            f_in_path = f_in.name
        
        del up_file
        purge()
        
        with st.spinner("Processing pages..."):
            try:
                final_path = get_optimized_pdf(f_in_path, 19.5)
                
                with open(final_path, "rb") as f:
                    final_bytes = f.read()
                
                final_mb = len(final_bytes) / (1024 * 1024)
                st.success(f"Output Size: {final_mb:.2f} MB")
                st.download_button("📥 Download PDF", final_bytes, "final_compressed.pdf")
                
                os.remove(f_in_path)
                os.remove(final_path)
                purge()
                
            except Exception as e:
                st.error(f"Error: {e}")
