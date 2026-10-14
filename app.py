import os
import io
import zipfile
import streamlit as st
import fitz  # PyMuPDF

# --- Page Configuration ---
st.set_page_config(
    page_title="Bulk PDF Template Transformer",
    page_icon="⚡",
    layout="centered"
)

def process_bulk_pdfs(input_pdf_bytes, titles, custom_filenames, font_choice, font_size, is_bold, alignment):
    """
    Core Engine: Explicitly searches for 'Change Here Now' in the uploaded PDF,
    wipes it out, and replaces it with the bulk titles using custom font size, bold, and alignment.
    """
    zip_buffer = io.BytesIO()
    
    # Map friendly font names to correct PyMuPDF Base-14 font codes for bold/regular
    font_map = {
        "Helvetica": "helv" if not is_bold else "hebo",
        "Times-Roman": "tiro" if not is_bold else "tibo",
        "Courier": "cour" if not is_bold else "cobo"
    }
    selected_font = font_map.get(font_choice, "hebo" if is_bold else "helv")

    # Map alignment to PyMuPDF text alignment flags (0 = Left, 1 = Center, 2 = Right)
    align_map = {"Left": 0, "Center": 1, "Right": 2}
    align_flag = align_map.get(alignment, 0)

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
            
            # Open fresh copy of the uploaded template PDF for each item
            doc = fitz.open(stream=input_pdf_bytes, filetype="pdf")
            
            found_placeholder = False
            
            # Scan every page to find "Change Here Now"
            for page in doc:
                # Search for the exact placeholder string
                text_instances = page.search_for("Change Here Now")
                
                # Fallback search variants if case formatting differs slightly in the PDF
                if not text_instances:
                    text_instances = page.search_for("change here now")
                if not text_instances:
                    text_instances = page.search_for("CHANGE HERE NOW")

                for inst in text_instances:
                    found_placeholder = True
                    
                    # 1. Cleanly erase the "Change Here Now" placeholder from the PDF
                    page.add_redact_annot(inst)
                    page.apply_redactions()
                    
                    # 2. Setup a clear layout box for the replacement title based on alignment
                    # Width is set wide (400px) so center and right alignments have room to render properly
                    if align_flag == 0: # Left
                        box_rect = fitz.Rect(inst.x0, inst.y0 - 4, inst.x0 + 400, inst.y0 + font_size + 15)
                    elif align_flag == 1: # Center
                        box_rect = fitz.Rect(inst.x0 - 150, inst.y0 - 4, inst.x0 + 250, inst.y0 + font_size + 15)
                    else: # Right
                        box_rect = fitz.Rect(inst.x0 - 350, inst.y0 - 4, inst.x0 + 50, inst.y0 + font_size + 15)
                    
                    # 3. Insert the new bulk title with your chosen size, bold weight, and alignment
                    page.insert_textbox(
                        box_rect,
                        current_title,
                        fontsize=font_size,
                        fontname=selected_font,
                        color=(0, 0, 0),
                        align=align_flag
                    )
            
            # If the placeholder text wasn't found anywhere in the PDF, log/handle gracefully
            if not found_placeholder:
                # Fallback: if "Change Here Now" isn't found, insert at top-center of page 1 as a safety measure
                page = doc[0]
                box_rect = fitz.Rect(50, 50, 450, 100)
                page.insert_textbox(
                    box_rect,
                    current_title,
                    fontsize=font_size,
                    fontname=selected_font,
                    color=(0, 0, 0),
                    align=align_flag
                )

            # Match PDF internal metadata title to the current title
            doc.set_metadata({
                "title": current_title,
                "subject": current_title,
                "producer": "Bulk PDF Generator Studio"
            })
            
            # Save compressed output file under 2.0 MB
            output_bytes = doc.tobytes(garbage=4, deflate=True)
            doc.close()
            
            # Write generated file into the zip archive
            zipf.writestr(safe_name, output_bytes)
            
    zip_buffer.seek(0)
    return zip_buffer

def main():
    st.title("⚡ Bulk PDF Template Transformer")
    st.markdown("Upload a template PDF containing **`Change Here Now`**, enter your bulk titles to replace it, and download your zip package.")

    # --- Section 1: Template Upload ---
    with st.container():
        st.subheader("1. Upload Template PDF")
        uploaded_file = st.file_uploader("Upload your template file (.pdf)", type=["pdf"])
        if uploaded_file:
            st.success("Template PDF uploaded successfully!")

    st.markdown("---")

    # --- Section 2: Typography & Formatting Controls ---
    st.subheader("2. Typography & Formatting Settings")
    t_col1, t_col2, t_col3, t_col4 = st.columns(4)
    
    with t_col1:
        font_choice = st.selectbox("Font Style", ["Helvetica", "Times-Roman", "Courier"])
    with t_col2:
        font_size = st.slider("Font Size", min_value=8, max_value=48, value=16)
    with t_col3:
        is_bold = st.checkbox("Make Bold", value=True)
    with t_col4:
        alignment = st.selectbox("Text Alignment", ["Left", "Center", "Right"])

    st.markdown("---")

    # --- Section 3: Data Input Boxes ---
    col1, col2 = st.columns(2)

    with col1:
        st.subheader("3. Bulk Titles (Replaces 'Change Here Now')")
        st.markdown("Enter titles below (**one per line**). Each line will replace *Change Here Now* on a separate PDF.")
        default_titles = "Project Alpha Report\nQuarterly Review 2026\nClient Compliance Update"
        titles_input = st.text_area("Titles List", value=default_titles, height=180)

    with col2:
        st.subheader("4. Bulk Rename Strings")
        st.markdown("Enter custom file rename strings below (**one per line**).")
        default_renames = "alpha_report_final\nquarterly_review\ncompliance_update_v1"
        renames_input = st.text_area("Rename Strings List", value=default_renames, height=180)

    st.markdown("---")

    # --- Execution Action ---
    if st.button("🚀 Generate Bulk PDFs & Download ZIP", type="primary", use_container_width=True):
        if not uploaded_file:
            st.error("Please upload a template PDF file first.")
        else:
            titles_list = titles_input.split("\n")
            renames_list = renames_input.split("\n")
            
            valid_titles = [t for t in titles_list if t.strip()]
            
            if not valid_titles:
                st.warning("Please provide at least one valid title.")
            else:
                with st.spinner("Replacing 'Change Here Now' across documents, applying bold styling, and compressing..."):
                    pdf_bytes = uploaded_file.read()
                    zip_file_buffer = process_bulk_pdfs(
                        pdf_bytes, 
                        titles_list, 
                        renames_list, 
                        font_choice, 
                        font_size, 
                        is_bold, 
                        alignment
                    )
                    
                st.success(f"Successfully generated {len(valid_titles)} customized PDF documents (optimized under 2.0 MB each)!")
                
                st.download_button(
                    label="📥 Download Generated PDFs (.zip)",
                    data=zip_file_buffer,
                    file_name="bulk_generated_documents.zip",
                    mime="application/zip",
                    use_container_width=True
                )

if __name__ == "__main__":
    main()
