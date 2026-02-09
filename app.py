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

# --- OPTIMIZED IMAGE-TARGETED COMPRESSION ---
def smart_object_compress(uploaded_file, target_mb):
    orig_mb = uploaded_file.size / (1024 * 1024)
    # Calculate quality (e.g., if target is 10% of orig, quality is 30%)
    quality_map = max(15, min(int((target_mb / orig_mb) * 100), 75))
    
    st.info(f"Targeting internal images with {quality_map}% quality. Text will remain sharp.")

    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as f_in:
        for chunk in uploaded_file:
            f_in.write(chunk)
        f_in_path = f_in.name

    try:
        doc = fitz.open(f_in_path)
        
        # Iterate through pages to find images
        for page in doc:
            image_list = page.get_images(full=True)
            
            for img in image_list:
                xref = img[0]  # The 'xref' index of the image object
                
                # Extract the existing image
                base_image = doc.extract_image(xref)
                if not base_image:
                    continue
                
                image_bytes = base_image["image"]
                
                # Compress the image using PIL
                pil_img = Image.open(BytesIO(image_bytes))
                
                # Convert to RGB if necessary (to allow JPEG saving)
                if pil_img.mode in ("RGBA", "P"):
                    pil_img = pil_img.convert("RGB")
                
                out_buffer = BytesIO()
                # Applying the calculated quality
                pil_img.save(out_buffer, format="JPEG", quality=quality_map, optimize=True)
                new_image_bytes = out_buffer.getvalue()
                
                # Replace the old heavy image with the small one in the PDF
                doc.update_stream(xref, new_image_bytes)
                
                # Crucial: Clean up PIL object
                pil_img.close()
                out_buffer.close()

        # Save with garbage=4 to actually delete the old uncompressed data
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as f_out:
            doc.save(f_out.name, garbage=4, deflate=True)
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
        st.error(f"Compression error: {e}")
        return None

# --- UI ---
st.set_page_config(page_title="PDF Smart Squeezer", layout="wide")
st.title("🎯 Smart PDF Compressor (Object-Based)")

up_pdf = st.file_uploader("Upload PDF (Max 500MB)", type="pdf")
target = st.number_input("Target Size (MB)", value=20, min_value=1)

if up_pdf and st.button("Run Smart Compression"):
    with st.spinner("Finding and shrinking heavy images..."):
        result = smart_object_compress(up_pdf, target)
        if result:
            new_size = len(result)/(1024*1024)
            st.success(f"Success! Final Size: {new_size:.2f} MB")
            st.download_button("Download Sharp PDF", result, f"compressed_{target}mb.pdf")
