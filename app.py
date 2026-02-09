import streamlit as st
import fitz  # PyMuPDF
import gc
import os
import tempfile
from PIL import Image
from io import BytesIO

# --- SYSTEM TWEAKS ---
st.cache_data.clear()
gc.collect()

def purge_memory():
    gc.collect()
    st.cache_data.clear()

def find_precision_settings(input_path, target_mb, use_grayscale):
    """
    Uses a binary search-style approach to find parameters that 
    land between 18.5MB and 19.8MB.
    """
    doc = fitz.open(input_path)
    total_pages = len(doc)
    sample_count = min(5, total_pages)
    
    # We aim for as close to 20MB as possible without exceeding it
    upper_limit = target_mb * 0.99  # 19.8 MB
    lower_limit = target_mb * 0.92  # 18.4 MB
    
    # Start with a high-quality baseline
    best_dpi = 72
    best_quality = 60
    
    # Binary search for DPI (Range: 30 to 200)
    low_dpi, high_dpi = 30, 200
    for _ in range(5):  # 5 iterations to narrow down DPI
        mid_dpi = (low_dpi + high_dpi) // 2
        
        sample_doc = fitz.open()
        cs = fitz.csGRAY if use_grayscale else fitz.csRGB
        for i in range(sample_count):
            page = doc[i]
            pix = page.get_pixmap(matrix=fitz.Matrix(mid_dpi/72, mid_dpi/72), colorspace=cs)
            img_data = pix.tobytes("jpg", jpg_quality=75) # Test with high quality
            new_page = sample_doc.new_page(width=page.rect.width, height=page.rect.height)
            new_page.insert_image(page.rect, stream=img_data)
        
        sample_buffer = BytesIO()
        sample_doc.save(sample_buffer, garbage=3)
        projected_mb = (sample_buffer.getbuffer().nbytes / sample_count) * total_pages / (1024 * 1024)
        sample_doc.close()
        
        if projected_mb > upper_limit:
            high_dpi = mid_dpi
        else:
            best_dpi = mid_dpi
            low_dpi = mid_dpi

    # Fine-tune Quality (Range: 30 to 95)
    low_q, high_q = 30, 95
    for _ in range(4):  # 4 iterations to narrow down Quality
        mid_q = (low_q + high_q) // 2
        
        sample_doc = fitz.open()
        for i in range(sample_count):
            page = doc[i]
            pix = page.get_pixmap(matrix=fitz.Matrix(best_dpi/72, best_dpi/72), colorspace=cs)
            img_data = pix.tobytes("jpg", jpg_quality=mid_q)
            new_page = sample_doc.new_page(width=page.rect.width, height=page.rect.height)
            new_page.insert_image(page.rect, stream=img_data)
        
        sample_buffer = BytesIO()
        sample_doc.save(sample_buffer, garbage=3)
        projected_mb = (sample_buffer.getbuffer().nbytes / sample_count) * total_pages / (1024 * 1024)
        sample_doc.close()
        
        if projected_mb > upper_limit:
            high_q = mid_q
        else:
            best_quality = mid_q
            low_q = mid_q
            
    doc.close()
    return best_dpi, best_quality

def process_full_pdf(input_path, dpi, quality, use_grayscale):
    doc = fitz.open(input_path)
    out_doc = fitz.open()
    colorspace = fitz.csGRAY if use_grayscale else fitz.csRGB
    
    progress_bar = st.progress(0, text=f"Applying Precision Settings: {dpi} DPI @ {quality}% Quality")
    
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
st.set_page_config(page_title="20MB Targeter", layout="wide")
st.title("🎯 Precision 20MB Targeter")

tab1, tab2 = st.tabs(["🗜️ Max-Quality Compressor", "🖼️ Images to PDF"])

with tab1:
    up_pdf = st.file_uploader("Upload PDF (Max 500MB)", type="pdf")
    use_grayscale = st.checkbox("Grayscale (Enable only if color isn't vital)", value=False)
    
    if up_pdf:
        if st.button("Optimize to ~20MB"):
            # Write upload to disk to save RAM
            with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as f_in:
                for chunk in up_pdf:
                    f_in.write(chunk)
                f_in_path = f_in.name
            
            # RAM Purge: Delete the original upload reference
            del up_pdf 
            purge_memory()
            
            try:
                with st.spinner("Finding optimal parameters..."):
                    # Find DPI and Quality that hit as close to 20MB as possible
                    winning_dpi, winning_q = find_precision_settings(f_in_path, 20, use_grayscale)
                
                with st.spinner(f"Finalizing at {winning_dpi} DPI..."):
                    final_path = process_full_pdf(f_in_path, winning_dpi, winning_q, use_grayscale)
                    
                    with open(final_path, "rb") as f:
                        final_data = f.read()
                    
                    size_mb = len(final_data)/(1024*1024)
                    st.success(f"Final Size: {size_mb:.2f} MB")
                    
                    st.download_button("Download Precision PDF", final_data, "precision_20mb.pdf")
                    
                    os.remove(f_in_path)
                    os.remove(final_path)
                    purge_memory()
                    
            except Exception as e:
                st.error(f"Error: {e}")

with tab2:
    # Standard stable Image-to-PDF logic
    imgs = st.file_uploader("Upload Images", type=["jpg", "png"], accept_multiple_files=True)
    if imgs and st.button("Convert to PDF"):
        pdf = fitz.open()
        for img_f in imgs:
            img_obj = Image.open(BytesIO(img_f.read())).convert("RGB")
            buf = BytesIO()
            img_obj.save(buf, format="JPEG", quality=85)
            p = pdf.new_page(width=img_obj.size[0], height=img_obj.size[1])
            p.insert_image(p.rect, stream=buf.getvalue())
            img_obj.close()
        st.download_button("Download PDF", pdf.tobytes(), "images.pdf")
        del imgs
        purge_memory()
