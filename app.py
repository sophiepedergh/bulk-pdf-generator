import io
import re
import zipfile
from pathlib import Path

import fitz  # PyMuPDF
import streamlit as st

# --------------------------------------------------
# CONFIGURATION
# --------------------------------------------------

PLACEHOLDER = "Replaced Title Here"
MAX_SIZE_BYTES = 2 * 1024 * 1024  # 2 MiB
FONT_DIR = Path(__file__).parent / "fonts"

st.set_page_config(
    page_title="Bulk PDF Generator",
    page_icon="📄",
    layout="wide",
)

# --------------------------------------------------
# HELPER FUNCTIONS
# --------------------------------------------------

def read_lines(text):
    """Read one non-empty value per line."""
    return [
        line.strip()
        for line in text.splitlines()
        if line.strip()
    ]


def safe_filename(value):
    """Sanitize a filename for common operating systems."""
    value = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", value)
    value = value.strip().rstrip(". ")
    return value[:180] or "document"


def unique_filename(name, used):
    """Avoid duplicate filenames in the output ZIP."""
    base = safe_filename(name)
    candidate = base
    counter = 2

    while candidate.casefold() in used:
        candidate = f"{base}_{counter}"
        counter += 1

    used.add(candidate.casefold())
    return candidate + ".pdf"


def find_bold_font():
    """
    Look for a bundled bold font.
    Place a compatible font at fonts/NotoSans-Bold.ttf.
    """
    candidates = [
        FONT_DIR / "NotoSans-Bold.ttf",
        FONT_DIR / "DejaVuSans-Bold.ttf",
        FONT_DIR / "Arial-Bold.ttf",
    ]

    for font_path in candidates:
        if font_path.is_file():
            return str(font_path)

    return None


def find_placeholder(page):
    """Find searchable occurrences of the placeholder."""
    return page.search_for(PLACEHOLDER)


def create_pdf(source_bytes, title, title_size, font_path=None):
    """
    Create a PDF with the placeholder replaced by a bold title.

    The title size is specified in PDF points. If the title
    cannot fit, the font size is reduced gradually.

    Note: replacement uses white redaction, so the template
    should have a plain white background behind the placeholder.
    """
    doc = fitz.open(
        stream=source_bytes,
        filetype="pdf",
    )

    try:
        if doc.needs_pass:
            raise ValueError(
                "The uploaded PDF is password-protected. "
                "Please upload an unlocked PDF."
            )

        occurrences = []

        for page_number, page in enumerate(doc):
            for rect in find_placeholder(page):
                occurrences.append(
                    (page_number, fitz.Rect(rect))
                )

        if not occurrences:
            raise ValueError(
                f'The text "{PLACEHOLDER}" was not found. '
                "Make sure the placeholder is searchable PDF text, "
                "not a scanned image or outlined text."
            )

        # Remove all original occurrences before adding replacements.
        for page_number, rect in occurrences:
            doc[page_number].add_redact_annot(
                rect,
                fill=(1, 1, 1),
                cross_out=False,
            )

        for page in doc:
            page.apply_redactions(
                images=0,
                graphics=0,
            )

        # Insert each title using a bold font.
        for page_number, original_rect in occurrences:
            page = doc[page_number]
            page_rect = page.rect

            rect = fitz.Rect(original_rect)

            # Extend the text area to the right for longer titles.
            rect.x1 = min(
                page_rect.x1 - 18,
                max(
                    rect.x1,
                    rect.x0 + 30,
                ),
            )

            # Give the title some extra vertical room.
            rect.y0 = max(
                0,
                rect.y0 - title_size * 0.5,
            )
            rect.y1 = min(
                page_rect.y1,
                rect.y1 + title_size * 0.8,
            )

            # Preserve the chosen size unless it cannot fit.
            font_size = float(title_size)
            inserted = False

            while font_size >= 5:
                kwargs = {
                    "fontsize": font_size,
                    "align": fitz.TEXT_ALIGN_LEFT,
                    "overlay": True,
                }

                if font_path:
                    kwargs["fontname"] = "CustomBold"
                    kwargs["fontfile"] = font_path
                else:
                    # Built-in Helvetica Bold.
                    kwargs["fontname"] = "hebo"

                result = page.insert_textbox(
                    rect,
                    title,
                    **kwargs,
                )

                if result >= 0:
                    inserted = True
                    break

                font_size -= 0.5

            if not inserted:
                raise ValueError(
                    f'Title "{title}" could not fit in the '
                    "available area, even after reducing the size. "
                    "Use a shorter title or adjust your PDF template."
                )

        # Update the PDF document metadata.
        metadata = doc.metadata
        metadata["title"] = title
        doc.set_metadata(metadata)

        # Save an optimized PDF.
        output = io.BytesIO()

        doc.save(
            output,
            garbage=4,
            deflate=True,
            clean=True,
        )

        return output.getvalue()

    finally:
        doc.close()


# --------------------------------------------------
# STREAMLIT USER INTERFACE
# --------------------------------------------------

st.title("📄 Bulk PDF Generator")
st.write(
    "Upload a PDF template, replace its title in bulk, "
    "rename the generated PDFs, and download them together."
)

st.info(
    'Your PDF template must contain the searchable text '
    '"Replaced Title Here".'
)

# 1. Upload PDF
st.subheader("1. Upload PDF Template")

uploaded_pdf = st.file_uploader(
    "Choose your original PDF",
    type=["pdf"],
)

# 2. Bulk titles and rename strings
st.subheader("2. Enter Bulk Titles and Rename Strings")

left_col, right_col = st.columns(2)

with left_col:
    titles_input = st.text_area(
        "Bulk titles — one title per line",
        height=260,
        placeholder=(
            "Stream\n"
            "𝐒𝐭𝐫𝐞𝐚𝐦\n"
            "Ｓｔｒｅａｍｉｎｇ\n"
            "My Fourth Title"
        ),
        help=(
            "Each non-empty line creates one PDF. "
            "Unicode title characters are retained."
        ),
    )

with right_col:
    names_input = st.text_area(
        "Bulk rename strings — one per line",
        height=260,
        placeholder=(
            "stream-guide\n"
            "bold-stream-guide\n"
            "streaming-guide\n"
            "fourth-document"
        ),
        help=(
            "Line 1 renames PDF 1, line 2 renames PDF 2, "
            "and so on. The .pdf extension is added automatically."
        ),
    )

titles = read_lines(titles_input)
rename_strings = read_lines(names_input)

# 3. Font settings
st.subheader("3. Title Formatting")

font_col, size_col = st.columns(2)

with font_col:
    st.text_input(
        "Title font style",
        value="Bold",
        disabled=True,
    )

    font_path = find_bold_font()

    if font_path:
        st.success(
            f"Custom bold font found: {Path(font_path).name}"
        )
    else:
        st.warning(
            "No custom font found. Using built-in Helvetica Bold. "
            "For broader Unicode coverage, add a compatible bold "
            "font to fonts/NotoSans-Bold.ttf."
        )

with size_col:
    size_option = st.selectbox(
        "Title font size",
        [
            "8 pt",
            "10 pt",
            "12 pt",
            "14 pt",
            "16 pt",
            "18 pt",
            "20 pt",
            "24 pt",
            "28 pt",
            "36 pt",
            "48 pt",
            "Custom",
        ],
        index=3,
    )

    if size_option == "Custom":
        title_size = st.number_input(
            "Custom title size (pt)",
            min_value=5.0,
            max_value=72.0,
            value=14.0,
            step=1.0,
        )
    else:
        title_size = float(
            size_option.replace(" pt", "")
        )

st.caption(
    f"Selected size: {title_size:g} pt. "
    "Long titles may use a smaller font if necessary to fit."
)

# 4. Input validation and summary
st.subheader("4. Batch Summary")

summary_col1, summary_col2, summary_col3 = st.columns(3)

summary_col1.metric(
    "Titles",
    len(titles),
)

summary_col2.metric(
    "Rename strings",
    len(rename_strings),
)

summary_col3.metric(
    "Selected font size",
    f"{title_size:g} pt",
)

can_generate = (
    uploaded_pdf is not None
    and len(titles) > 0
    and len(titles) == len(rename_strings)
)

if titles and rename_strings and len(titles) != len(rename_strings):
    st.error(
        "The number of titles and rename strings must match. "
        "Please provide one rename string for every title."
    )

if not titles:
    st.caption("Enter at least one title to enable generation.")

# --------------------------------------------------
# GENERATION
# --------------------------------------------------

st.subheader("5. Generate PDFs")

if st.button(
    "🚀 Generate PDFs",
    type="primary",
    use_container_width=True,
    disabled=not can_generate,
):
    source_bytes = uploaded_pdf.getvalue()

    # Reset results for a new batch.
    generated = []
    failures = []
    used_filenames = set()

    try:
        # Validate the PDF.
        with fitz.open(
            stream=source_bytes,
            filetype="pdf",
        ) as check_doc:
            if check_doc.needs_pass:
                st.error(
                    "This PDF is password-protected. "
                    "Upload an unlocked PDF."
                )
                st.stop()

            has_placeholder = any(
                find_placeholder(page)
                for page in check_doc
            )

        if not has_placeholder:
            st.error(
                f'The placeholder "{PLACEHOLDER}" was not found. '
                "Please check the uploaded PDF."
            )
            st.stop()

        progress = st.progress(0)
        status = st.empty()

        for index, (title, rename) in enumerate(
            zip(titles, rename_strings),
            start=1,
        ):
            status.write(
                f"Processing {index}/{len(titles)}: {title}"
            )

            try:
                pdf_bytes = create_pdf(
                    source_bytes=source_bytes,
                    title=title,
                    title_size=title_size,
                    font_path=font_path,
                )

                size_bytes = len(pdf_bytes)
                size_mib = size_bytes / (1024 * 1024)

                if size_bytes > MAX_SIZE_BYTES:
                    failures.append({
                        "title": title,
                        "filename": rename,
                        "reason": (
                            f"Output is {size_mib:.3f} MiB. "
                            "The maximum allowed size is 2 MiB."
                        ),
                    })
                else:
                    filename = unique_filename(
                        rename,
                        used_filenames,
                    )

                    generated.append({
                        "filename": filename,
                        "title": title,
                        "data": pdf_bytes,
                        "size_bytes": size_bytes,
                    })

            except Exception as exc:
                failures.append({
                    "title": title,
                    "filename": rename,
                    "reason": str(exc),
                })

            progress.progress(
                index / len(titles)
            )

        progress.empty()
        status.empty()

        st.session_state["generated_pdfs"] = generated
        st.session_state["pdf_failures"] = failures

    except Exception as exc:
        st.error(f"Unable to process the batch: {exc}")


# --------------------------------------------------
# RESULTS AND DOWNLOADS
# --------------------------------------------------

generated = st.session_state.get(
    "generated_pdfs",
    [],
)

failures = st.session_state.get(
    "pdf_failures",
    [],
)

if generated or failures:
    st.divider()
    st.subheader("6. Generation Results")

    result_col1, result_col2 = st.columns(2)

    result_col1.metric(
        "Successful PDFs",
        len(generated),
    )

    result_col2.metric(
        "Failed or oversized",
        len(failures),
    )

    if generated:
        st.success(
            f"{len(generated)} PDF(s) generated successfully."
        )

        # Create ZIP in memory.
        zip_buffer = io.BytesIO()

        with zipfile.ZipFile(
            zip_buffer,
            mode="w",
            compression=zipfile.ZIP_DEFLATED,
        ) as archive:
            for item in generated:
                archive.writestr(
                    item["filename"],
                    item["data"],
                )

        st.download_button(
            label="⬇️ Download All PDFs (ZIP)",
            data=zip_buffer.getvalue(),
            file_name="bulk_generated_pdfs.zip",
            mime="application/zip",
            type="primary",
            use_container_width=True,
        )

        with st.expander("View successful files"):
            for item in generated:
                size_mib = (
                    item["size_bytes"] / (1024 * 1024)
                )

                st.write(
                    f"✅ **{item['filename']}** — "
                    f"{size_mib:.3f} MiB — "
                    f"Title: {item['title']}"
                )

        with st.expander("Download individual PDFs"):
            for index, item in enumerate(generated):
                st.download_button(
                    label=f"Download {item['filename']}",
                    data=item["data"],
                    file_name=item["filename"],
                    mime="application/pdf",
                    key=f"individual_pdf_{index}",
                    use_container_width=True,
                )

    if failures:
        st.warning(
            f"{len(failures)} file(s) failed or exceeded the size limit."
        )

        with st.expander("View errors"):
            for item in failures:
                st.error(
                    f"**{item['filename']}** "
                    f"(Title: {item['title']})\n\n"
                    f"{item['reason']}"
                )

    st.caption(
        "The 2 MiB limit is checked for each PDF individually. "
        "Oversized files are excluded from the ZIP rather than "
        "being presented as compliant."
    )

st.divider()

st.caption(
    "Bulk PDF Generator · Python + Streamlit + PyMuPDF"
)
