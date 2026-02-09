import streamlit as st
import fitz  # PyMuPDF
import gc
import zipfile
from io import BytesIO
from PIL import Image

# --- 1. SESSION RESILIENCE GUARD ---
# This block detects a fresh load or a refresh and clears old cache/state
if 'app_init' not in st.session_state:
    st.cache_data.clear()
    st.cache_resource.clear()
    gc.collect()
    st.session_state['app_init'] = True

def force_restart():
    """Manual reset button logic to fix any stuck states."""
    for key in st.session_state.keys():
        del st.session_state[key]
    st.cache_data.clear()
    st.rerun()

# --- CORE FUNCTIONS ---

@st.cache_data(show_spinner=False)
def get_predicted_settings(input_bytes, target_mb):
    """Calculates optimal DPI based on the target file size."""
    try:
        doc = fitz.open(stream=input_bytes, filetype="pdf")
        orig_mb = len(input_bytes) / (1024 * 1024)
        
        ratio = (target_mb / orig_mb) ** 0.5
        predicted_dpi = int(72 * ratio * 1.2)
        predicted_dpi = max(45, min(predicted_dpi, 150))
        
        page = doc[0]
        zoom = predicted_dpi / 72
        mat = fitz.Matrix(zoom, zoom)
        pix = page.get_pixmap(matrix=mat)
        img = Image.open(BytesIO(pix.tobytes("png")))
        
        doc.close()
        return predicted_dpi, img
    except Exception as e:
        return 72, None

def compress_single_pdf(input_bytes, dpi, quality=60):
    """Processes PDF page-by-page to keep RAM usage low."""
    try:
        doc = fitz.open(stream=input_bytes, filetype="pdf")
        new_doc = fitz.open()
        
        for page in doc:
            zoom = dpi / 72
            mat = fitz.Matrix(zoom, zoom)
            pix = page.get_pixmap(matrix=mat)
            img_data = pix.tobytes("jpg", jpg_quality=quality)
            
            new_page = new_doc.new_page(width=page.rect.width, height=page.rect.height)
            new_page.insert_image(page.rect, stream=img_data)
            pix = None 
            
        out_buf = BytesIO()
        new_doc.save(out_buf, garbage=4, deflate=True)
        new_doc.close()
        doc.close()
        gc.collect() 
        return out_buf.getvalue()
    except Exception:
        st.error("Session timed out. Please re-upload your file.")
        return None

# --- UI LAYOUT ---

st.set_page_config(page_title="PDF Power Tool", layout="wide", page_icon="📄")

# Sidebar reset for easy access
with st.sidebar:
    st.title("Settings")
    if st.button("🔄 Reset App & Cache"):
        force_restart()
    st.divider()

st.title("🚀 PDF Power Tool")
st.markdown("Compress large PDFs or convert images to PDF. Optimized for files up to 500MB.")

tab1, tab2 = st.tabs(["🗜️ Bulk PDF Compressor", "🖼️ Images to PDF"])

# --- TAB 1: PDF COMPRESSION ---
with tab1:
    st.header("Bulk PDF Compressor")
    uploaded_pdfs = st.file_uploader("Upload PDFs (Max 500MB/file)", type="pdf", accept_multiple_files=True, key="compressor_upload")
    
    if uploaded_pdfs:
        target_mb = st.sidebar.number_input("Target Size per file (MB):", min_value=1, value=20)
        
        if st.sidebar.button("Calculate & Preview Settings"):
            with st.spinner("Analyzing first file..."):
                dpi, img = get_predicted_settings(uploaded_pdfs[0].getvalue(), target_mb)
                st.session_state['bulk_dpi'] = dpi
                st.sidebar.image(img, caption=f"Preview @ {dpi} DPI", use_container_width=True)
                st.sidebar.success(f"Calculated DPI: {dpi}")

        if 'bulk_dpi' in st.session_state:
            if st.button(f"Compress {len(uploaded_pdfs)} PDF(s)"):
                zip_buffer = BytesIO()
                progress_text = st.empty()
                
                with zipfile.ZipFile(zip_buffer, "w") as zf:
                    for i, up_file in enumerate(uploaded_pdfs):
                        progress_text.text(f"Processing ({i+1}/{len(uploaded_pdfs)}): {up_file.name}")
                        data = compress_single_pdf(up_file.getvalue(), st.session_state['bulk_dpi'])
                        if data:
                            zf.writestr(f"compressed_{up_file.name}", data)
                
                st.success("✅ Compression complete!")
                st.download_button(
                    label="📥 Download All (ZIP)",
                    data=zip_buffer.getvalue(),
                    file_name="compressed_pdfs.zip",
                    mime="application/zip"
                )

# --- TAB 2: IMAGES TO PDF ---
with tab2:
    st.header("Images to PDF Converter")
    uploaded_imgs = st.file_uploader("Select Images (JPG/PNG)", type=["jpg", "jpeg", "png"], accept_multiple_files=True, key="image_upload")
    
    if uploaded_imgs:
        pdf_name = st.text_input("Filename (without .pdf):", value="my_images")
        
        if st.button("Convert Images to PDF"):
            with st.spinner("Processing images..."):
                new_pdf = fitz.open()
                
                for img_file in uploaded_imgs:
                    try:
                        raw_data = img_file.read()
                        img = Image.open(BytesIO(raw_data))
                        
                        if img.mode in ("RGBA", "P"):
                            img = img.convert("RGB")
                        
                        img_buffer = BytesIO()
                        img.save(img_buffer, format="JPEG", quality=85)
                        
                        page = new_pdf.new_page(width=img.size[0], height=img.size[1])
                        page.insert_image(page.rect, stream=img_buffer.getvalue())
                        
                        img.close()
                    except Exception as e:
                        st.error(f"Error processing {img_file.name}: {e}")
                
                if len(new_pdf) > 0:
                    out_pdf = BytesIO()
                    new_pdf.save(out_pdf, garbage=4, deflate=True)
                    new_pdf.close()
                    st.success(f"✅ Created PDF with {len(uploaded_imgs)} pages.")
                    st.download_button("📥 Download PDF", out_pdf.getvalue(), f"{pdf_name}.pdf")
                else:
                    st.error("No valid images found to convert.")
