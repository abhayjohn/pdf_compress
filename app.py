import streamlit as st
import fitz  # PyMuPDF
import gc
import os
import tempfile
from PIL import Image
from io import BytesIO

# --- SYSTEM TWEAKS ---
st.cache_data.clear()
gc.collect()

def hard_force_compress(uploaded_file, target_mb=19):
    orig_mb = uploaded_file.size / (1024 * 1024)
    # Aggressive quality for large files
    quality_val = 25 if orig_mb > 100 else 40
    
    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as f_in:
        for chunk in uploaded_file:
            f_in.write(chunk)
        f_in_path = f_in.name

    try:
        doc = fitz.open(f_in_path)
        
        for page in doc:
            # Get all images on the page
            image_info = page.get_image_info(hashes=False)
            
            for img in image_info:
                xref = img["xref"]
                if xref == 0: continue # Skip inline images
                
                # Extract and Compress
                base_image = doc.extract_image(xref)
                if not base_image: continue
                
                pil_img = Image.open(BytesIO(base_image["image"]))
                
                # Convert to RGB to ensure no transparency bugs (which cause blank pages)
                if pil_img.mode != "RGB":
                    pil_img = pil_img.convert("RGB")
                
                # Resizing: If the image is physically huge, scale it down
                if pil_img.width > 1500:
                    scale = 1500 / pil_img.width
                    new_size = (1500, int(pil_img.height * scale))
                    pil_img = pil_img.resize(new_size, Image.Resampling.LANCZOS)

                img_buf = BytesIO()
                pil_img.save(img_buf, format="JPEG", quality=quality_val, optimize=True)
                
                # UPDATE THE IMAGE STREAM
                doc.update_stream(xref, img_buf.getvalue())
                
                # Update object properties to ensure it's recognized as a JPEG
                doc.set_object_value(xref, "/Subtype", "/Image")
                doc.set_object_value(xref, "/Filter", "/DCTDecode")
                doc.set_object_value(xref, "/ColorSpace", "/DeviceRGB")
                doc.set_object_value(xref, "/BitsPerComponent", "8")
                
                pil_img.close()
                img_buf.close()

        # Final save with maximum cleanup
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as f_out:
            # garbage=4 and clean=True are non-negotiable for size reduction
            doc.save(f_out.name, garbage=4, deflate=True, clean=True)
            f_out_path = f_out.name
        
        doc.close()
        with open(f_out_path, "rb") as f:
            final_data = f.read()

        os.remove(f_in_path)
        os.remove(f_out_path)
        gc.collect()
        return final_data

    except Exception as e:
        if 'f_in_path' in locals() and os.path.exists(f_in_path): os.remove(f_in_path)
        st.error(f"Processing Error: {e}")
        return None

# --- UI LAYOUT ---
st.set_page_config(page_title="PDF Fixer", layout="wide")
st.title("🎯 Pro PDF Compressor (Anti-Blank Fix)")

up_pdf = st.file_uploader("Upload PDF", type="pdf")

if up_pdf:
    st.write(f"Original Size: {up_pdf.size / (1024*1024):.2f} MB")
    if st.button("Compress & Fix"):
        with st.spinner("Re-encoding images and cleaning PDF structure..."):
            result = hard_force_compress(up_pdf)
            if result:
                new_size = len(result)/(1024*1024)
                st.success(f"Final Size: {new_size:.2f} MB")
                st.download_button("Download Fixed PDF", result, "compressed_fixed.pdf")
