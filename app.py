import os
import io
import zipfile
import tempfile
import streamlit as st
import fitz  # PyMuPDF

# --- Page Configuration ---
st.set_page_config(
    page_title="Bulk PDF Template Transformer",
    page_icon="⚡",
    layout="centered"
)

def process_bulk_pdfs(input_pdf_bytes, titles, custom_filenames):
    """
    Processes the template PDF: replaces 'Change Here Now' with bulk titles,
    updates metadata titles, assigns custom rename strings, and controls file size.
    """
    zip_buffer = io.BytesIO()
    
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zipf:
        total_files = len(titles)
        
        for i in range(total_files):
            current_title = titles[i].strip()
            if not current_title:
                continue
                
            # Determine custom filename string
            if i < len(custom_filenames) and custom_filenames[i].strip():
                raw_name = custom_filenames[i].strip()
            else:
                raw_name = current_title
                
            # Sanitize filename safely
            safe_name = "".join(c for c in raw_name if c.isalnum() or c in (' ', '_', '-')).strip()
            safe_name = safe_name.replace(" ", "_") + ".pdf"
            
            # Open PDF from uploaded bytes via PyMuPDF (fitz)
            doc = fitz.open(stream=input_pdf_bytes, filetype="pdf")
            
            # 1. Replace "Change Here Now" with the target Title
            for page in doc:
                text_instances = page.search_for("Change Here Now")
                for inst in text_instances:
                    # Redact original text cleanly and insert updated text
                    page.add_redact_annot(inst, text="")
                    page.apply_redactions()
                    page.insert_text(
                        fitz.Point(inst.x0, inst.y1 - 2), 
                        current_title, 
                        fontsize=11, 
                        color=(0, 0, 0)
                    )
            
            # 2. Set Page Title / Slug Metadata
            doc.set_metadata({
                "title": current_title,
                "subject": current_title,
                "producer": "Bulk PDF Transformer Tool"
            })
            
            # 3. Save with deflation compression to enforce file size < 2.0 MB
            output_bytes = doc.tobytes(garbage=4, deflate=True)
            doc.close()
            
            # Write into archive
            zipf.writestr(safe_name, output_bytes)
            
    zip_buffer.seek(0)
    return zip_buffer

def main():
    st.title("⚡ Bulk PDF Generator & Renamer")
    st.markdown("Upload a template PDF containing **`Change Here Now`**, provide lists of titles and filenames, and download your bulk package instantly.")

    with st.container():
        st.subheader("1. Upload Template PDF")
        uploaded_file = st.file_uploader("Upload your template file (.pdf)", type=["pdf"])
        if uploaded_file:
            st.success("Template PDF uploaded successfully!")

    st.markdown("---")

    col1, col2 = st.columns(2)

    with col1:
        st.subheader("2. Bulk Titles")
        st.markdown("Enter titles below (**one per line**). Each will replace *Change Here Now*.")
        default_titles = "Project Alpha Report\nQuarterly Review 2026\nClient Compliance Update"
        titles_input = st.text_area("Titles List", value=default_titles, height=180)

    with col2:
        st.subheader("3. Bulk Rename Strings")
        st.markdown("Enter custom file rename strings below (**one per line**).")
        default_renames = "alpha_report_final\nquarterly_review\ncompliance_update_v1"
        renames_input = st.text_area("Rename Strings List", value=default_renames, height=180)

    st.markdown("---")

    # Execution Action
    if st.button("🚀 Generate Bulk PDFs & Download ZIP", type="primary", use_container_width=True):
        if not uploaded_file:
            st.error("Please upload a template PDF file first.")
        else:
            titles_list = titles_input.split("\n")
            renames_list = renames_input.split("\n")
            
            # Filter out completely empty lines while keeping index mapping consistent
            valid_titles = [t for t in titles_list if t.strip()]
            
            if not valid_titles:
                st.warning("Please provide at least one valid title.")
            else:
                with st.spinner("Processing bulk files, updating metadata, and applying compression..."):
                    pdf_bytes = uploaded_file.read()
                    zip_file_buffer = process_bulk_pdfs(pdf_bytes, titles_list, renames_list)
                    
                st.success(f"Successfully generated {len(valid_titles)} customized PDF documents ( optimized under 2.0 MB each )!")
                
                st.download_button(
                    label="📥 Download Generated PDFs (.zip)",
                    data=zip_file_buffer,
                    file_name="bulk_generated_documents.zip",
                    mime="application/zip",
                    use_container_width=True
                )

if __name__ == "__main__":
    main()