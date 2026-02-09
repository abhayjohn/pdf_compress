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
    quality_val = 20 if orig_mb > 150 else 35
    
    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as f_in:
        for chunk in uploaded_file:
            f_in.write(chunk)
        f_in_path = f_in.name

    try:
        doc = fitz.open(f_in_path)
        
        for page in doc:
            # get_images is more stable than get_image_info for xrefs
            image_list = page.get_images(full=True)
            
            for img_item in image_list:
                xref = img_item[0] # The first element is always the xref
                
                if xref == 0: continue 
                
                try:
                    base_image = doc.extract_image(xref)
                    if not base_image: continue
                    
                    pil_img = Image.open(BytesIO(base_image["image"]))
                    
                    # Force RGB to prevent blank pages from CMYK/Alpha issues
                    if pil_img.mode != "RGB":
                        pil_img = pil_img.convert("RGB")
                    
                    # Physical downscaling if image is huge
                    if pil_img.width > 1200:
                        scale = 1200 / pil_img.width
                        new_size = (1200, int(pil_img.height * scale))
                        pil_img = pil_img.resize(new_size, Image.Resampling.LANCZOS)

                    img_buf = BytesIO()
                    pil_img.save(img_buf, format="JPEG", quality=quality_val, optimize=True)
                    
                    # Update object stream
                    doc.update_stream(xref, img_buf.getvalue())
                    
                    # Force PDF metadata to recognize the new stream format
                    doc.set_object_value(xref, "/Subtype", "/Image")
                    doc.set_object_value(xref, "/Filter", "/DCTDecode")
                    doc.set_object_value(xref, "/ColorSpace", "/DeviceRGB")
                    
                    pil_img.close()
                    img_buf.close()
                except:
                    continue # Skip problematic small icons/masks

        # Final save with maximum cleanup
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as f_out:
            # clean=True and garbage=4 are the keys to the <20MB goal
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
st.set_page_config(page_title="PDF Power Tool", layout="wide")

tab1, tab2 = st.tabs(["🗜️ Ultra Compressor (<20MB)", "🖼️ Images to PDF"])

with tab1:
    st.title("🎯 Force 20MB Compressor")
    up_pdf = st.file_uploader("Upload PDF (Max 500MB)", type="pdf", key="pdf_tab")
    
    if up_pdf:
        st.write(f"Original Size: {up_pdf.size / (1024*1024):.2f} MB")
        if st.button("Compress Now"):
            with st.spinner("Executing deep compression..."):
                result = hard_force_compress(up_pdf)
                if result:
                    res_mb = len(result)/(1024*1024)
                    st.success(f"Final Size: {res_mb:.2f} MB")
                    st.download_button("Download Compressed PDF", result, "final_compressed.pdf")

with tab2:
    st.title("🖼️ Image to PDF Converter")
    imgs = st.file_uploader("Upload Images", type=["jpg", "png"], accept_multiple_files=True, key="img_tab")
    if imgs and st.button("Convert to PDF"):
        new_pdf = fitz.open()
        for img_f in imgs:
            img_obj = Image.open(BytesIO(img_f.read())).convert("RGB")
            buf = BytesIO()
            img_obj.save(buf, format="JPEG", quality=70)
            p = new_pdf.new_page(width=img_obj.size[0], height=img_obj.size[1])
            p.insert_image(p.rect, stream=buf.getvalue())
            img_obj.close()
        st.download_button("Download PDF", new_pdf.tobytes(), "images.pdf")
