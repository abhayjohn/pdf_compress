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

def reboot_logic():
    st.session_state.clear()
    st.cache_data.clear()
    st.rerun()

# --- OPTIMIZED IMAGE-TARGETED COMPRESSION ---
def smart_object_compress(uploaded_file, target_mb):
    """
    Compresses by targeting internal images specifically.
    This keeps text sharp while reducing file size significantly.
    """
    orig_mb = uploaded_file.size / (1024 * 1024)
    # Scale quality based on how much we need to shrink
    # If shrinking 200MB to 20MB, we need aggressive (30-40) quality
    quality_map = max(20, min(int((target_mb / orig_mb) * 100), 70))
    
    st.info(f"Targeting internal objects with {quality_map}% image quality to maintain text clarity.")

    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as f_in:
        for chunk in uploaded_file:
            f_in.write(chunk)
        f_in_path = f_in.name

    try:
        doc = fitz.open(f_in_path)
        
        # We iterate through every object in the PDF
        for xref in range(1, doc.xref_length()):
            if doc.is_image(xref):
                # Extract the image
                pix = fitz.Pixmap(doc, xref)
                
                # Convert to JPEG with the target quality
                # This is where the 200MB -> 20MB reduction happens
                img_data = pix.tobytes("jpg", jpg_quality=quality_map)
                
                # Replace the old heavy image with the new compressed one
                doc.update_stream(xref, img_data)
                
                # Update the object metadata to tell PDF it's now a JPEG
                doc.set_object_value(xref, "/Subtype", "/Image")
                doc.set_object_value(xref, "/Filter", "/DCTDecode")
                
                pix = None
                if xref % 10 == 0: gc.collect()

        # Save the result
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as f_out:
            # garbage=4 is critical here to remove the old uncompressed image data
            doc.save(f_out.name, garbage=4, deflate=True)
            f_out_path = f_out.name
        
        doc.close()

        with open(f_out_path, "rb") as f:
            final_data = f.read()

        os.remove(f_in_path)
        os.remove(f_out_path)
        return final_data

    except Exception as e:
        if 'f_in_path' in locals() and os.path.exists(f_in_path): os.remove(f_in_path)
        st.error(f"Compression error: {e}")
        return None

# --- UI ---
st.set_page_config(page_title="PDF Smart Squeezer", layout="wide")

st.title("🎯 Smart PDF Compressor (High Clarity)")
st.markdown("This version preserves **text sharpness** and only compresses the images inside the PDF.")

tab1, tab2 = st.tabs(["🗜️ Smart Compressor", "🖼️ Image Converter"])

with tab1:
    up_pdf = st.file_uploader("Upload PDF (Max 500MB)", type="pdf")
    target = st.number_input("Target Size (MB)", value=20, min_value=1)
    
    if up_pdf and st.button("Run Smart Compression"):
        with st.spinner("Analyzing and shrinking images..."):
            result = smart_object_compress(up_pdf, target)
            if result:
                new_size = len(result)/(1024*1024)
                st.success(f"Success! Final Size: {new_size:.2f} MB")
                st.download_button("Download Sharp PDF", result, f"sharp_compressed_{target}mb.pdf")

with tab2:
    # (The Image to PDF logic remains the same as it was working)
    imgs = st.file_uploader("Upload Images", type=["jpg", "png"], accept_multiple_files=True)
    if imgs and st.button("Convert to PDF"):
        pdf = fitz.open()
        for img_f in imgs:
            img_obj = Image.open(img_f).convert("RGB")
            buf = BytesIO()
            img_obj.save(buf, format="JPEG", quality=75)
            p = pdf.new_page(width=img_obj.size[0], height=img_obj.size[1])
            p.insert_image(p.rect, stream=buf.getvalue())
            img_obj.close()
        st.download_button("Download PDF", pdf.tobytes(), "images.pdf")
