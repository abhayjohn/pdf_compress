import streamlit as st
import fitz
import gc
import zipfile
from io import BytesIO
from PIL import Image

def get_predicted_dpi(input_bytes, target_mb):
    """Predicts DPI based on file size ratio."""
    doc = fitz.open(stream=input_bytes, filetype="pdf")
    orig_mb = len(input_bytes) / (1024 * 1024)
    ratio = (target_mb / orig_mb) ** 0.5
    predicted_dpi = int(72 * ratio * 1.2)
    predicted_dpi = max(45, min(predicted_dpi, 150))
    
    # Get first page for preview
    page = doc[0]
    pix = page.get_pixmap(matrix=fitz.Matrix(predicted_dpi/72, predicted_dpi/72))
    img = Image.open(BytesIO(pix.tobytes("png")))
    doc.close()
    return predicted_dpi, img

def compress_single_pdf(input_bytes, dpi, quality=60):
    """Processes one PDF page by page to save RAM."""
    doc = fitz.open(stream=input_bytes, filetype="pdf")
    new_doc = fitz.open()
    
    for page in doc:
        zoom = dpi / 72
        mat = fitz.Matrix(zoom, zoom)
        pix = page.get_pixmap(matrix=mat)
        img_data = pix.tobytes("jpg", jpg_quality=quality)
        
        new_page = new_doc.new_page(width=page.rect.width, height=page.rect.height)
        new_page.insert_image(page.rect, stream=img_data)
        pix = None # Release memory
        
    out_buf = BytesIO()
    new_doc.save(out_buf, garbage=4, deflate=True)
    new_doc.close()
    doc.close()
    gc.collect() # Force clean up
    return out_buf.getvalue()

# --- UI ---
st.set_page_config(page_title="Bulk PDF Squeezer", layout="wide")
st.title("📚 Bulk PDF Ultra-Compressor")

uploaded_files = st.file_uploader("Upload PDF files (Max 500MB per file)", type="pdf", accept_multiple_files=True)

if uploaded_files:
    target_mb = st.sidebar.number_input("Target Size per file (MB):", min_value=1, value=20)
    
    # 1. Preview Step (Using the first file)
    if st.sidebar.button("Generate Preview for First File"):
        first_file = uploaded_files[0].getvalue()
        dpi, img = get_predicted_dpi(first_file, target_mb)
        st.session_state['bulk_dpi'] = dpi
        st.sidebar.image(img, caption=f"Preview at {dpi} DPI", use_container_width=True)

    # 2. Bulk Processing
    if 'bulk_dpi' in st.session_state:
        if st.button(f"Compress {len(uploaded_files)} Files"):
            processed_files = []
            progress_bar = st.progress(0)
            
            for idx, uploaded_file in enumerate(uploaded_files):
                st.write(f"⏳ Processing: {uploaded_file.name}...")
                file_bytes = uploaded_file.getvalue()
                
                compressed_data = compress_single_pdf(file_bytes, st.session_state['bulk_dpi'])
                processed_files.append((uploaded_file.name, compressed_data))
                
                # Update progress
                progress_bar.progress((idx + 1) / len(uploaded_files))
            
            # 3. Create ZIP for download
            zip_buffer = BytesIO()
            with zipfile.ZipFile(zip_buffer, "w") as zip_file:
                for name, data in processed_files:
                    zip_file.writestr(f"compressed_{name}", data)
            
            st.success("✅ All files processed!")
            st.download_button(
                label="📥 Download All as ZIP",
                data=zip_buffer.getvalue(),
                file_name="compressed_pdfs.zip",
                mime="application/zip"
            )
