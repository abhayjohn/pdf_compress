import streamlit as st
import fitz  # PyMuPDF
import gc
import os
import tempfile

def purge():
    gc.collect()

def fast_compress(input_path, dpi, quality):
    doc = fitz.open(input_path)
    out_doc = fitz.open()
    
    progress_bar = st.progress(0)
    status_text = st.empty()
    total_pages = len(doc)

    for i, page in enumerate(doc):
        status_text.text(f"Processing page {i+1} of {total_pages}...")
        
        # Calculate scaling based on DPI
        zoom = dpi / 72
        mat = fitz.Matrix(zoom, zoom)
        
        # Render page to image
        pix = page.get_pixmap(matrix=mat, colorspace=fitz.csRGB)
        img_data = pix.tobytes("jpg", jpg_quality=quality)
        
        # Insert into new PDF
        new_page = out_doc.new_page(width=page.rect.width, height=page.rect.height)
        new_page.insert_image(page.rect, stream=img_data)
        
        pix = None  # Free memory
        progress_bar.progress((i + 1) / total_pages)
        
        if i % 20 == 0:
            gc.collect()

    out_path = tempfile.mktemp(suffix=".pdf")
    out_doc.save(out_path, garbage=4, deflate=True)
    
    doc.close()
    out_doc.close()
    return out_path

# --- UI Layout ---
st.set_page_config(page_title="Pro PDF Compressor", page_icon="⚡")
st.title("⚡ Pro PDF Compressor")

# Sidebar for Settings
st.sidebar.header("Compression Settings")
mode = st.sidebar.select_slider(
    "Select Quality Level",
    options=["Extreme", "Recommended", "High Quality"],
    value="Recommended"
)

# Map modes to technical values
settings = {
    "Extreme": {"dpi": 60, "quality": 30},
    "Recommended": {"dpi": 75, "quality": 50},
    "High Quality": {"dpi": 120, "quality": 75}
}

st.sidebar.info(f"DPI: {settings[mode]['dpi']} | JPEG Quality: {settings[mode]['quality']}%")

up_file = st.file_uploader("Upload your PDF file", type="pdf")

if up_file:
    if st.button("Start Compression"):
        # Save upload to disk
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as f_in:
            f_in.write(up_file.getbuffer())
            f_in_path = f_in.name
        
        final_path = None
        try:
            # Run compression with user settings
            final_path = fast_compress(
                f_in_path, 
                settings[mode]["dpi"], 
                settings[mode]["quality"]
            )
            
            with open(final_path, "rb") as f:
                final_bytes = f.read()
            
            orig_size = os.path.getsize(f_in_path) / (1024 * 1024)
            new_size = len(final_bytes) / (1024 * 1024)
            
            st.success(f"Compression Complete! {orig_size:.1f}MB → {new_size:.1f}MB")
            st.download_button("📥 Download Compressed PDF", final_bytes, "compressed.pdf")
            
        except Exception as e:
            st.error(f"Error: {e}")
        
        finally:
            # Cleanup
            if os.path.exists(f_in_path): os.remove(f_in_path)
            if final_path and os.path.exists(final_path): os.remove(final_path)
            purge()
