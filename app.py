import streamlit as st
import fitz
import gc
import zipfile
from io import BytesIO
from PIL import Image

# --- Helper Functions ---

def get_predicted_dpi(input_bytes, target_mb):
    doc = fitz.open(stream=input_bytes, filetype="pdf")
    orig_mb = len(input_bytes) / (1024 * 1024)
    ratio = (target_mb / orig_mb) ** 0.5
    predicted_dpi = int(72 * ratio * 1.2)
    predicted_dpi = max(45, min(predicted_dpi, 150))
    page = doc[0]
    pix = page.get_pixmap(matrix=fitz.Matrix(predicted_dpi/72, predicted_dpi/72))
    img = Image.open(BytesIO(pix.tobytes("png")))
    doc.close()
    return predicted_dpi, img

def compress_single_pdf(input_bytes, dpi, quality=60):
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

# --- UI Setup ---
st.set_page_config(page_title="PDF Power Tool", layout="wide")
tab1, tab2 = st.tabs(["🗜️ Bulk Compressor", "🖼️ Images to PDF"])

# --- TAB 1: COMPRESSOR ---
with tab1:
    st.header("Bulk PDF Compressor")
    uploaded_pdfs = st.file_uploader("Upload PDFs (Max 500MB/file)", type="pdf", accept_multiple_files=True, key="pdf_uploader")
    
    if uploaded_pdfs:
        target_mb = st.sidebar.number_input("Target Size (MB):", min_value=1, value=20)
        if st.sidebar.button("Preview Settings"):
            dpi, img = get_predicted_dpi(uploaded_pdfs[0].getvalue(), target_mb)
            st.session_state['bulk_dpi'] = dpi
            st.sidebar.image(img, caption=f"Preview @ {dpi} DPI")

        if 'bulk_dpi' in st.session_state and st.button("Start Bulk Compression"):
            zip_buffer = BytesIO()
            with zipfile.ZipFile(zip_buffer, "w") as zf:
                for up_file in uploaded_pdfs:
                    with st.status(f"Compressing {up_file.name}..."):
                        data = compress_single_pdf(up_file.getvalue(), st.session_state['bulk_dpi'])
                        zf.writestr(f"small_{up_file.name}", data)
            st.success("All files compressed!")
            st.download_button("📥 Download ZIP", zip_buffer.getvalue(), "compressed_files.zip")

# --- TAB 2: IMAGES TO PDF ---
with tab2:
    st.header("Convert Images to PDF")
    st.write("Upload multiple images (JPG/PNG) to combine them into a single PDF.")
    
    uploaded_imgs = st.file_uploader("Select Images", type=["jpg", "jpeg", "png"], accept_multiple_files=True)
    
    if uploaded_imgs:
        st.write(f"📸 {len(uploaded_imgs)} images selected.")
        pdf_name = st.text_input("Output PDF Name:", value="converted_images")
        
        if st.button("Convert to PDF"):
            with st.spinner("Building PDF..."):
                new_pdf = fitz.open()
                
                for img_file in uploaded_imgs:
                    img_bytes = img_file.getvalue()
                    # Open image with PIL to get dimensions
                    img = Image.open(BytesIO(img_bytes))
                    width, height = img.size
                    
                    # Create page with image dimensions
                    page = new_pdf.new_page(width=width, height=height)
                    page.insert_image(page.rect, stream=img_bytes)
                    img.close()
                
                pdf_output = BytesIO()
                new_pdf.save(pdf_output)
                new_pdf.close()
                gc.collect()
                
                st.success("✅ PDF Created Successfully!")
                st.download_button(
                    label="📥 Download PDF",
                    data=pdf_output.getvalue(),
                    file_name=f"{pdf_name}.pdf",
                    mime="application/pdf"
                )
