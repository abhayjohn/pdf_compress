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

def purge_memory():
    gc.collect()
    st.cache_data.clear()

def find_precision_settings(input_path, target_mb, use_grayscale):
    """
    Finds the exact DPI and Quality to hit as close to 20MB as possible.
    """
    doc = fitz.open(input_path)
    total_pages = len(doc)
    sample_count = min(5, total_pages)
    
    # Target 19.5MB to leave just a tiny bit of room for PDF metadata
    precision_target = target_mb * 0.975 
    
    best_dpi = 30
    best_quality = 40

    # Step 1: Find the best DPI first with standard quality (60)
    # We use smaller increments (10 DPI) for precision
    for test_dpi in [150, 140, 130, 120, 110, 100, 90, 80, 70, 60, 50, 40, 30]:
        sample_doc = fitz.open()
        cs = fitz.csGRAY if use_grayscale else fitz.csRGB
        for i in range(sample_count):
            page = doc[i]
            pix = page.get_pixmap(matrix=fitz.Matrix(test_dpi/72, test_dpi/72), colorspace=cs)
            img_data = pix.tobytes("jpg", jpg_quality=60)
            new_page = sample_doc.new_page(width=page.rect.width, height=page.rect.height)
            new_page.insert_image(page.rect, stream=img_data)
        
        sample_buffer = BytesIO()
        sample_doc.save(sample_buffer, garbage=3)
        projected_mb = (sample_buffer.getbuffer().nbytes / sample_count) * total_pages / (1024 * 1024)
        sample_doc.close()
        
        if projected_mb <= precision_target:
            best_dpi = test_dpi
            # Step 2: Now fine-tune the quality for this DPI
            # If we are at 15MB, bump quality up to get closer to 20MB
            if projected_mb < (precision_target * 0.8):
                best_quality = 80
            elif projected_mb < (precision_target * 0.9):
                best_quality = 70
            else:
                best_quality = 60
            break
            
    doc.close()
    return best_dpi, best_quality

def process_full_pdf(input_path, dpi, quality, use_grayscale):
    doc = fitz.open(input_path)
    out_doc = fitz.open()
    colorspace = fitz.csGRAY if use_grayscale else fitz.csRGB
    
    progress_bar = st.progress(0, text=f"Fine-tuning Quality... ({dpi} DPI @ {quality}% Quality)")
    
    for i, page in enumerate(doc):
        mat = fitz.Matrix(dpi/72, dpi/72)
        pix = page.get_pixmap(matrix=mat, colorspace=colorspace)
        img_data = pix.tobytes("jpg", jpg_quality=quality)
        
        new_page = out_doc.new_page(width=page.rect.width, height=page.rect.height)
        new_page.insert_image(page.rect, stream=img_data)
        
        pix = None
        if i % 3 == 0: gc.collect()
        progress_bar.progress((i + 1) / len(doc))

    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as f_out:
        out_doc.save(f_out.name, garbage=4, deflate=True)
        out_path = f_out.name
    
    out_doc.close()
    doc.close()
    return out_path

# --- UI LAYOUT ---
st.set_page_config(page_title="Precision PDF", layout="wide")
st.title("🎯 Precision 20MB PDF Compressor")

tab1, tab2 = st.tabs(["🗜️ High-Accuracy Compressor", "🖼️ Images to PDF"])

with tab1:
    up_pdf = st.file_uploader("Upload PDF (Max 500MB)", type="pdf")
    use_grayscale = st.checkbox("Grayscale Mode", value=False) # Turned off by default for better color
    
    if up_pdf:
        if st.button("Compress & Clear RAM"):
            with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as f_in:
                for chunk in up_pdf:
                    f_in.write(chunk)
                f_in_path = f_in.name
            
            # RAM Purge
            del up_pdf 
            purge_memory()
            
            try:
                with st.spinner("Calculating precision parameters..."):
                    # Finding the perfect balance
                    winning_dpi, winning_q = find_precision_settings(f_in_path, 20, use_grayscale)
                
                with st.spinner(f"Finalizing at {winning_dpi} DPI..."):
                    final_path = process_full_pdf(f_in_path, winning_dpi, winning_q, use_grayscale)
                    
                    with open(final_path, "rb") as f:
                        final_data = f.read()
                    
                    st.success(f"Final Size: {len(final_data)/(1024*1024):.2f} MB")
                    st.download_button("Download Precision PDF", final_data, "precision_20mb.pdf")
                    
                    os.remove(f_in_path)
                    os.remove(final_path)
                    purge_memory()
                    
            except Exception as e:
                st.error(f"Error: {e}")

with tab2:
    imgs = st.file_uploader("Upload Images", type=["jpg", "png"], accept_multiple_files=True)
    if imgs and st.button("Convert & Purge"):
        pdf = fitz.open()
        for img_f in imgs:
            img_obj = Image.open(BytesIO(img_f.read())).convert("RGB")
            buf = BytesIO()
            img_obj.save(buf, format="JPEG", quality=85) # High quality for images-to-pdf
            p = pdf.new_page(width=img_obj.size[0], height=img_obj.size[1])
            p.insert_image(p.rect, stream=buf.getvalue())
            img_obj.close()
        st.download_button("Download PDF", pdf.tobytes(), "images.pdf")
        del imgs
        purge_memory()
