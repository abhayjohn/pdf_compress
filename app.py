import streamlit as st
import fitz
import gc
from io import BytesIO

def compress_iteration(input_bytes, quality, dpi):
    """Single compression attempt with specific quality/dpi."""
    doc = fitz.open(stream=input_bytes, filetype="pdf")
    new_doc = fitz.open()
    for page in doc:
        zoom = dpi / 72
        mat = fitz.Matrix(zoom, zoom)
        pix = page.get_pixmap(matrix=mat)
        img_data = pix.tobytes("jpg", jpg_quality=quality)
        new_page = new_doc.new_page(width=page.rect.width, height=page.rect.height)
        new_page.insert_image(page.rect, stream=img_data)
    
    out_buf = BytesIO()
    new_doc.save(out_buf, garbage=4, deflate=True)
    new_doc.close()
    doc.close()
    return out_buf.getvalue()

def smart_compress(input_bytes, target_mb):
    """Iteratively reduces quality until target size is met."""
    # Settings to try: (Quality, DPI)
    # Starts at high quality, moves to 'extreme'
    presets = [
        (80, 150), (60, 120), (40, 96), (30, 75), (20, 72), (10, 50)
    ]
    
    last_data = input_bytes
    for q, d in presets:
        st.write(f"Trying: Quality {q}%, DPI {d}...")
        compressed_data = compress_iteration(input_bytes, q, d)
        current_size = len(compressed_data) / (1024 * 1024)
        
        last_data = compressed_data
        if current_size <= target_mb:
            return compressed_data, current_size
            
    return last_data, len(last_data) / (1024 * 1024)

# --- Streamlit UI ---
st.title("🎯 Target-Size PDF Compressor")

uploaded_file = st.file_uploader("Upload PDF (Up to 500MB)", type="pdf")

if uploaded_file:
    orig_bytes = uploaded_file.getvalue()
    orig_mb = len(orig_bytes) / (1024 * 1024)
    st.info(f"Original Size: {orig_mb:.2f} MB")

    # The Option to change Target Size
    target_mb = st.number_input("Enter Target Size (MB):", min_value=1, max_value=int(orig_mb), value=20)

    if st.button("Compress to Target"):
        with st.spinner("Searching for best compression level..."):
            final_data, final_size = smart_compress(orig_bytes, target_mb)
            
            if final_size <= target_mb:
                st.success(f"Success! Final Size: {final_size:.2f} MB")
            else:
                st.warning(f"Could only reach {final_size:.2f} MB without making it unreadable.")

            st.download_button("Download Result", final_data, f"compressed_{target_mb}mb.pdf")
