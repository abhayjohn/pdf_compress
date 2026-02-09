import streamlit as st
import fitz  # PyMuPDF
import gc
import os
import tempfile
from io import BytesIO
from PIL import Image

# --- 1. SYSTEM TWEAKS ---
# Clear memory globally on startup
st.cache_data.clear()
gc.collect()

def reboot_logic():
    st.session_state.clear()
    st.cache_data.clear()
    st.rerun()

# --- 2. OOM-SAFE COMPRESSION ENGINE ---
def oom_safe_compress(uploaded_file, target_mb):
    """Uses disk-mapping to avoid the 1GB RAM limit."""
    
    # Estimate DPI but strictly cap it at 75 for safety
    orig_mb = uploaded_file.size / (1024 * 1024)
    ratio = (target_mb / orig_mb) ** 0.5
    safe_dpi = max(30, min(int(72 * ratio), 75))
    
    st.warning(f"OOM Protection Active: Using {safe_dpi} DPI to stay within 1GB RAM.")

    # Step 1: Write upload to disk immediately to free RAM
    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as f_in:
        # Using a chunked write to prevent RAM spikes during file copy
        for chunk in uploaded_file:
            f_in.write(chunk)
        f_in_path = f_in.name

    try:
        # Step 2: Open PDF from disk (not memory)
        doc = fitz.open(f_in_path)
        out_doc = fitz.open()

        progress_bar = st.progress(0, text="Squeezing pages...")
        total = len(doc)

        for i, page in enumerate(doc):
            # Render page at low resolution
            mat = fitz.Matrix(safe_dpi / 72, safe_dpi / 72)
            pix = page.get_pixmap(matrix=mat, colorspace=fitz.csRGB)
            
            # Compress image data immediately
            img_bits = pix.tobytes("jpg", jpg_quality=40)
            
            # Build new PDF
            new_page = out_doc.new_page(width=page.rect.width, height=page.rect.height)
            new_page.insert_image(page.rect, stream=img_bits)
            
            # Step 3: Explicit Deletion for OOM prevention
            pix = None
            img_bits = None
            
            # Force RAM release every page
            if i % 1 == 0:
                gc.collect()
            
            progress_bar.progress((i + 1) / total)

        # Step 4: Save result to disk
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as f_out:
            out_doc.save(f_out.name, garbage=4, deflate=True)
            f_out_path = f_out.name
        
        out_doc.close()
        doc.close()

        # Final Read
        with open(f_out_path, "rb") as f:
            final_data = f.read()

        # Cleanup
        os.remove(f_in_path)
        os.remove(f_out_path)
        return final_data

    except Exception as e:
        if 'f_in_path' in locals() and os.path.exists(f_in_path): os.remove(f_in_path)
        st.error(f"Memory Crash Avoided, but error occurred: {e}")
        return None

# --- UI ---
st.set_page_config(page_title="PDF Survivor Pro", width="wide")

with st.sidebar:
    st.title("Admin")
    if st.button("Clear RAM/Restart"):
        reboot_logic()

st.title("🗜️ Ultra-Stable PDF Compressor")
st.caption("Designed for 500MB+ files on limited-RAM servers.")

tab1, tab2 = st.tabs(["🗜️ Compressor", "🖼️ Image Converter"])

with tab1:
    up_pdf = st.file_uploader("Upload large PDF", type="pdf")
    target = st.number_input("Target Size (MB)", value=20, min_value=1)
    
    if up_pdf and st.button("Run Safe Compression"):
        result = oom_safe_compress(up_pdf, target)
        if result:
            st.success(f"Success! Size: {len(result)/(1024*1024):.2f} MB")
            st.download_button("Download PDF", result, "compressed.pdf")

with tab2:
    imgs = st.file_uploader("Upload Images", type=["jpg", "png"], accept_multiple_files=True)
    if imgs and st.button("Convert to PDF"):
        pdf = fitz.open()
        for img_f in imgs:
            # Low-RAM image processing
            img_obj = Image.open(img_f).convert("RGB")
            buf = BytesIO()
            img_obj.save(buf, format="JPEG", quality=60)
            p = pdf.new_page(width=img_obj.size[0], height=img_obj.size[1])
            p.insert_image(p.rect, stream=buf.getvalue())
            img_obj.close()
            gc.collect()
        st.download_button("Download PDF", pdf.tobytes(), "images.pdf")
