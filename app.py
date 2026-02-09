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

def smart_object_compress(uploaded_file, target_mb=19):
    orig_mb = uploaded_file.size / (1024 * 1024)
    
    # Pass 1: Extremely aggressive quality mapping
    # We aim for slightly under 20 (19MB) to stay safe
    quality_map = max(10, min(int((target_mb / orig_mb) * 100), 50))
    
    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as f_in:
        for chunk in uploaded_file:
            f_in.write(chunk)
        f_in_path = f_in.name

    try:
        doc = fitz.open(f_in_path)
        
        for page in doc:
            image_list = page.get_images(full=True)
            for img in image_list:
                xref = img[0]
                base_image = doc.extract_image(xref)
                if not base_image:
                    continue
                
                pil_img = Image.open(BytesIO(base_image["image"]))
                
                # RE-SIZING LOGIC: If file is huge, physically shrink image dimensions
                if orig_mb > 100:
                    # Reduce dimensions by 50% for huge files
                    new_size = (int(pil_img.width * 0.7), int(pil_img.height * 0.7))
                    pil_img = pil_img.resize(new_size, Image.Resampling.LANCZOS)

                if pil_img.mode in ("RGBA", "P"):
                    pil_img = pil_img.convert("RGB")
                
                out_buffer = BytesIO()
                # Save with aggressive JPEG settings
                pil_img.save(out_buffer, format="JPEG", quality=quality_map, optimize=True, progressive=True)
                
                # Replace the object
                doc.update_stream(xref, out_buffer.getvalue())
                
                pil_img.close()
                out_buffer.close()

        # Final save with maximum cleanup
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as f_out:
            # garbage=4 is essential to purge the heavy data
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
        st.error(f"Compression error: {e}")
        return None

# --- UI LAYOUT ---
st.set_page_config(page_title="20MB Force Squeezer", layout="wide")
st.title("🎯 The 20MB Hard-Limit Compressor")
st.markdown("This tool forces PDFs (up to 500MB) to stay near or below **20MB** by resizing internal assets.")

tab1, tab2 = st.tabs(["🗜️ Force 20MB Compression", "🖼️ Images to PDF"])

with tab1:
    up_pdf = st.file_uploader("Upload PDF", type="pdf", key="pdf_force")
    if up_pdf:
        st.info(f"Current Size: {up_pdf.size / (1024*1024):.2f} MB")
        if st.button("Force Compress to < 20MB"):
            with st.spinner("Executing high-intensity compression..."):
                result = smart_object_compress(up_pdf, 19)
                if result:
                    res_size = len(result)/(1024*1024)
                    st.success(f"Final Size: {res_size:.2f} MB")
                    if res_size > 22:
                        st.warning("File is extremely dense. Try running the output through again for a second pass.")
                    st.download_button("Download Compressed PDF", result, "final_under_20mb.pdf")

with tab2:
    # (Image to PDF logic remains stable)
    uploaded_imgs = st.file_uploader("Select Images", type=["jpg", "png"], accept_multiple_files=True, key="img_conv")
    if uploaded_imgs and st.button("Create PDF"):
        new_pdf = fitz.open()
        for img_file in uploaded_imgs:
            img_pil = Image.open(BytesIO(img_file.read()))
            if img_pil.mode != "RGB": img_pil = img_pil.convert("RGB")
            img_buf = BytesIO()
            img_pil.save(img_buf, format="JPEG", quality=60)
            page = new_pdf.new_page(width=img_pil.size[0], height=img_pil.size[1])
            page.insert_image(page.rect, stream=img_buf.getvalue())
            img_pil.close()
        st.download_button("Download PDF", new_pdf.tobytes(), "images.pdf")
