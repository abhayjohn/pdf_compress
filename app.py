import streamlit as st
import fitz
import gc
from io import BytesIO
from PIL import Image

def get_preview(input_bytes, target_mb):
    doc = fitz.open(stream=input_bytes, filetype="pdf")
    orig_mb = len(input_bytes) / (1024 * 1024)
    
    # Predictive DPI Formula
    ratio = (target_mb / orig_mb) ** 0.5
    predicted_dpi = int(72 * ratio * 1.2)
    predicted_dpi = max(40, min(predicted_dpi, 150))
    
    # Generate preview of the first page
    page = doc[0]
    zoom = predicted_dpi / 72
    mat = fitz.Matrix(zoom, zoom)
    pix = page.get_pixmap(matrix=mat)
    
    # Convert to PIL Image for Streamlit display
    img = Image.open(BytesIO(pix.tobytes("png")))
    doc.close()
    return img, predicted_dpi

def run_full_compression(input_bytes, dpi, quality=60):
    doc = fitz.open(stream=input_bytes, filetype="pdf")
    new_doc = fitz.open()
    
    progress_bar = st.progress(0)
    total_pages = len(doc)

    for i, page in enumerate(doc):
        zoom = dpi / 72
        mat = fitz.Matrix(zoom, zoom)
        pix = page.get_pixmap(matrix=mat)
        img_data = pix.tobytes("jpg", jpg_quality=quality)
        
        new_page = new_doc.new_page(width=page.rect.width, height=page.rect.height)
        new_page.insert_image(page.rect, stream=img_data)
        
        # Update progress
        progress_bar.progress((i + 1) / total_pages)
        pix = None
        if i % 10 == 0: gc.collect()

    out_buf = BytesIO()
    new_doc.save(out_buf, garbage=4, deflate=True)
    new_doc.close()
    doc.close()
    return out_buf.getvalue()

# --- UI Layout ---
st.set_page_config(page_title="Smart PDF Squeezer", layout="wide")
st.title("⚡ Predictive PDF Compressor with Preview")

uploaded_file = st.file_uploader("Upload PDF (Up to 500MB)", type="pdf")

if uploaded_file:
    file_bytes = uploaded_file.getvalue()
    orig_mb = len(file_bytes) / (1024 * 1024)
    
    col1, col2 = st.columns([1, 1])

    with col1:
        st.info(f"📁 **Original Size:** {orig_mb:.2f} MB")
        target_mb = st.number_input("Target Size (MB):", min_value=1, value=20)
        
        if st.button("Generate Preview"):
            with st.spinner("Calculating quality..."):
                preview_img, calc_dpi = get_preview(file_bytes, target_mb)
                st.session_state['preview'] = preview_img
                st.session_state['dpi'] = calc_dpi

    if 'preview' in st.session_state:
        with col2:
            st.subheader(f"Preview (at {st.session_state['dpi']} DPI)")
            st.image(st.session_state['preview'], use_container_width=True)
            st.caption("If this looks too blurry, increase your Target Size.")

        if st.button("Looks Good - Compress Full File"):
            with st.spinner("Squeezing every page..."):
                final_pdf = run_full_compression(file_bytes, st.session_state['dpi'])
                final_size = len(final_pdf) / (1024 * 1024)
                st.success(f"Final Size: {final_size:.2f} MB")
                st.download_button("Download Compressed PDF", final_pdf, "compressed.pdf")
