import streamlit as st
import fitz
import gc
import os
import tempfile
import pandas as pd
import zipfile
from io import BytesIO

def purge():
    gc.collect()

def fast_compress(input_path, dpi, quality):
    doc = fitz.open(input_path)
    out_doc = fitz.open()
    
    for page in doc:
        zoom = dpi / 72
        mat = fitz.Matrix(zoom, zoom)
        pix = page.get_pixmap(matrix=mat, colorspace=fitz.csRGB)
        img_data = pix.tobytes("jpg", jpg_quality=quality)
        
        new_page = out_doc.new_page(width=page.rect.width, height=page.rect.height)
        new_page.insert_image(page.rect, stream=img_data)
        pix = None

    out_path = tempfile.mktemp(suffix=".pdf")
    out_doc.save(out_path, garbage=4, deflate=True)
    doc.close()
    out_doc.close()
    return out_path

# --- UI Layout ---
st.set_page_config(page_title="PDF Batch Power-Tool", page_icon="📦")
st.title("📦 PDF Batch Power-Tool")

st.sidebar.header("Compression Settings")
mode = st.sidebar.select_slider(
    "Quality Level",
    options=["Extreme", "Recommended", "High Quality"],
    value="Recommended"
)

settings = {
    "Extreme": {"dpi": 60, "quality": 30},
    "Recommended": {"dpi": 75, "quality": 50},
    "High Quality": {"dpi": 120, "quality": 75}
}

up_files = st.file_uploader("Upload PDF(s)", type="pdf", accept_multiple_files=True)

if up_files:
    if st.button(f"🚀 Compress & Zip {len(up_files)} Files"):
        results = []
        zip_buffer = BytesIO()
        
        # Create a ZIP file in memory
        with zipfile.ZipFile(zip_buffer, "w") as zf:
            overall_progress = st.progress(0)
            status_text = st.empty()
            
            for idx, up_file in enumerate(up_files):
                status_text.text(f"Processing: {up_file.name}")
                
                with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as f_in:
                    f_in.write(up_file.getbuffer())
                    f_in_path = f_in.name
                
                try:
                    # Compress
                    comp_path = fast_compress(f_in_path, settings[mode]["dpi"], settings[mode]["quality"])
                    
                    # Add to ZIP
                    zf.write(comp_path, arcname=f"compressed_{up_file.name}")
                    
                    # Log Stats
                    orig_size = os.path.getsize(f_in_path) / (1024 * 1024)
                    new_size = os.path.getsize(comp_path) / (1024 * 1024)
                    results.append({
                        "File Name": up_file.name,
                        "Original (MB)": round(orig_size, 2),
                        "Compressed (MB)": round(new_size, 2),
                        "Reduction": f"{round((1 - new_size/orig_size)*100)}%"
                    })
                    
                    os.remove(comp_path) # Clean up individual compressed file
                except Exception as e:
                    st.error(f"Error with {up_file.name}: {e}")
                finally:
                    os.remove(f_in_path)
                    purge()
                    overall_progress.progress((idx + 1) / len(up_files))
            
            status_text.text("✅ All files processed!")

        # Final UI presentation
        if results:
            st.divider()
            st.subheader("Summary Report")
            st.table(pd.DataFrame(results))
            
            # Download ZIP button
            st.download_button(
                label="📥 Download All (ZIP)",
                data=zip_buffer.getvalue(),
                file_name="compressed_pdfs.zip",
                mime="application/zip"
            )
