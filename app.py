import streamlit as st
import fitz  # PyMuPDF
import gc
import os
import tempfile
from PIL import Image
from io import BytesIO

# --- 1. SYSTEM TWEAKS ---
st.cache_data.clear()
gc.collect()

def find_best_dpi(input_path, target_mb):
    """
    Quickly tests DPI settings on a small sample of the PDF 
    to predict the final size without crashing the RAM.
    """
    doc = fitz.open(input_path)
    total_pages = len(doc)
    # Sample only up to 5 pages to save time/RAM
    sample_count = min(5, total_pages)
    
    best_dpi = 45 # Default fallback
    # Test common DPI steps from high to low
    for test_dpi in [150, 120, 96, 72, 60, 45]:
        sample_doc = fitz.open()
        for i in range(sample_count):
            page = doc[i]
            pix = page.get_pixmap(matrix=fitz.Matrix(test_dpi/72, test_dpi/72))
            img_data = pix.tobytes("jpg", jpg_quality=50)
            new_page = sample_doc.new_page(width=page.rect.width, height=page.rect.height)
            new_page.insert_image(page.rect, stream=img_data)
        
        sample_buffer = BytesIO()
        sample_doc.save(sample_buffer, garbage=3)
        # Estimate total size based on sample ratio
        projected_size = (sample_buffer.getbuffer().nbytes / sample_count) * total_pages
        projected_mb = projected_size / (1024 * 1024)
        
        sample_doc.close()
        if projected_mb <= target_mb:
            best_dpi = test_dpi
            break
            
    doc.close()
    return best_dpi

def process_full_pdf(input_path, dpi, target_mb):
    """
    Re-renders the PDF at the chosen DPI. This is the 'safest' way
    to ensure no black/static images appear.
    """
    doc = fitz.open(input_path)
    out_doc = fitz.open()
    
    # Adjust quality based on DPI to squeeze extra space
    quality = 40 if dpi < 75 else 60
    
    progress_bar = st.progress(0, text=f"Applying {dpi} DPI compression...")
    
    for i, page in enumerate(doc):
        # Render page to image (This fixes the 'black image' corruption)
        mat = fitz.Matrix(dpi/72, dpi/72)
        pix = page.get_pixmap(matrix=mat, colorspace=fitz.csRGB)
        img_data = pix.tobytes("jpg", jpg_quality=quality)
        
        new_page = out_doc.new_page(width=page.rect.width, height=page.rect.height)
        new_page.insert_image(page.rect, stream=img_data)
        
        # Immediate memory release
        pix = None
        if i % 2 == 0: gc.collect()
        progress_bar.progress((i + 1) / len(doc))

    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as f_out:
        out_doc.save(f_out.name, garbage=4, deflate=True)
        out_path = f_out.name
    
    out_doc.close()
    doc.close()
    return out_path

# --- UI LAYOUT ---
st.set_page_config(page_title="PDF Survivor", layout="wide")
st.title("🎯 Smart Iterative PDF Compressor")
st.markdown("Finds the best DPI to hit your target size without corrupting images.")

up_pdf = st.file_uploader("Upload PDF (Up to 500MB)", type="pdf")

if up_pdf:
    target_mb = st.number_input("Target Size (MB)", value=20, min_value=1)
    
    if st.button("Calculate & Compress"):
        # Step 1: Save to disk to free RAM
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as f_in:
            for chunk in up_pdf:
                f_in.write(chunk)
            f_in_path = f_in.name
            
        try:
            with st.spinner("Finding optimal DPI settings..."):
                winning_dpi = find_best_dpi(f_in_path, target_mb)
                st.success(f"Optimal Resolution Found: {winning_dpi} DPI")
            
            with st.spinner("Generating final PDF..."):
                final_path = process_full_pdf(f_in_path, winning_dpi, target_mb)
                
                with open(final_path, "rb") as f:
                    final_data = f.read()
                
                final_mb = len(final_data) / (1024 * 1024)
                st.info(f"Final Size: {final_mb:.2f} MB")
                st.download_button("Download Compressed PDF", final_data, "compressed.pdf")
                
                # Cleanup
                os.remove(final_path)
        except Exception as e:
            st.error(f"Error: {e}")
        finally:
            if os.path.exists(f_in_path): os.remove(f_in_path)
