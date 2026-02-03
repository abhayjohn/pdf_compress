import streamlit as st
import fitz  # PyMuPDF
from io import BytesIO

def compress_pdf(input_bytes, quality, dpi):
    """
    Core compression logic:
    - Opens PDF from memory
    - Iterates through pages and downsamples images
    - Saves with 'garbage collection' to strip metadata/unused objects
    """
    doc = fitz.open(stream=input_bytes, filetype="pdf")
    new_doc = fitz.open()

    for page in doc:
        # Scale factor based on DPI (72 is standard PDF resolution)
        zoom = dpi / 72
        mat = fitz.Matrix(zoom, zoom)
        
        # Convert page to image
        pix = page.get_pixmap(matrix=mat)
        
        # Compress image into JPEG format
        img_data = pix.tobytes("jpg", jpg_quality=quality)
        
        # Create new page in output doc and insert the "shrunk" image
        new_page = new_doc.new_page(width=page.rect.width, height=page.rect.height)
        new_page.insert_image(page.rect, stream=img_data)

    output_buffer = BytesIO()
    # garbage=4: Eliminate duplicate objects and unused resources
    # deflate=True: Compress the resulting stream
    new_doc.save(output_buffer, garbage=4, deflate=True)
    new_doc.close()
    doc.close()
    return output_buffer.getvalue()

# --- Streamlit UI Setup ---
st.set_page_config(page_title="PDF Squeezer Pro", page_icon="🗜️")

st.title("🗜️ PDF Ultra-Compressor")
st.markdown("""
Upload files up to **150MB**. This tool uses image downsampling to reach targets near **20MB**.
""")

# File Uploader
uploaded_file = st.file_uploader("Upload your large PDF", type="pdf")

if uploaded_file:
    # Calculate original size
    original_bytes = uploaded_file.getvalue()
    original_size_mb = len(original_bytes) / (1024 * 1024)
    
    st.info(f"📂 **Original Size:** {original_size_mb:.2f} MB")

    # Compression Level Presets
    mode = st.radio("Compression Intensity:", 
                    ["Standard (Better Quality)", "Extreme Squeeze (Smallest Size)"])

    if mode == "Standard (Better Quality)":
        quality = 60
        dpi = 120
    else:
        # Lower DPI and lower JPEG quality to hit the ~20MB target
        quality = 30
        dpi = 75

    if st.button("Start Compression"):
        if original_size_mb > 160:
            st.warning("This file is quite large. It may take a minute...")

        with st.spinner("Processing..."):
            try:
                compressed_pdf_data = compress_pdf(original_bytes, quality, dpi)
                compressed_size_mb = len(compressed_pdf_data) / (1024 * 1024)
                
                # Show results
                st.success(f"✅ Done! New Size: **{compressed_size_mb:.2f} MB**")
                
                # Reduction percentage
                reduction = (1 - (compressed_size_mb / original_size_mb)) * 100
                st.write(f"📉 Reduced by: **{reduction:.1f}%**")

                st.download_button(
                    label="📥 Download Compressed PDF",
                    data=compressed_pdf_data,
                    file_name=f"compressed_{uploaded_file.name}",
                    mime="application/pdf"
                )
            except Exception as e:
                st.error(f"Error processing PDF: {e}")

st.divider()
st.caption("Note: This method converts pages to images. Text will still be visible but not selectable.")
