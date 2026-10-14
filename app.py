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

    while (candidate + ".pdf").casefold() in used:
        candidate = f"{base}_{counter}"
        counter += 1

    filename = candidate + ".pdf"
    used.add(filename.casefold())
    return filename


def find_bold_font():
    """Find an optional bundled bold font."""
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


def create_pdf(
    source_bytes,
    title,
    title_size,
    alignment="Center",
    font_path=None,
):
    """
    Replace placeholder text with a bold title.

    The title area spans nearly the entire page width.
    Font size is reduced only when needed to fit the title
    on one line, while preserving the selected alignment.
    """

    doc = fitz.open(
        stream=source_bytes,
        filetype="pdf",
    )

    try:
        if doc.needs_pass:
            raise ValueError(
                "The PDF is password-protected. "
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
                "Make sure it is searchable PDF text, "
                "not a scanned image or outlined text."
            )

        # Remove all original occurrences.
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

        # Select horizontal text alignment.
        alignment_map = {
            "Left": fitz.TEXT_ALIGN_LEFT,
            "Center": fitz.TEXT_ALIGN_CENTER,
            "Right": fitz.TEXT_ALIGN_RIGHT,
        }

        text_alignment = alignment_map.get(
            alignment,
            fitz.TEXT_ALIGN_CENTER,
        )

        # Insert each replacement title.
        for page_number, original_rect in occurrences:
            page = doc[page_number]
            page_rect = page.rect

            # Use almost the entire page width.
            margin = 36  # 36 points = 0.5 inch

            rect = fitz.Rect(
                margin,
                max(
                    0,
                    original_rect.y0 - title_size * 0.5,
                ),
                page_rect.width - margin,
                min(
                    page_rect.height,
                    original_rect.y1 + title_size * 0.8,
                ),
            )

            # Keep the title vertically near its original position.
            # Use a taller area when large fonts are selected.
            rect.y0 = max(
                0,
                original_rect.y0 - title_size * 0.6,
            )
            rect.y1 = min(
                page_rect.height,
                original_rect.y1 + title_size * 0.9,
            )

            # Start with the user's selected font size.
            font_size = float(title_size)
            inserted = False

            while font_size >= 5:
                kwargs = {
                    "fontsize": font_size,
                    "align": text_alignment,
                    "overlay": True,
                }

                if font_path:
                    kwargs["fontname"] = "CustomBold"
                    kwargs["fontfile"] = font_path
                else:
                    kwargs["fontname"] = "hebo"

                # insert_textbox returns a negative value if
                # the text does not fit inside the rectangle.
                result = page.insert_textbox(
                    rect,
                    title,
                    **kwargs,
                )

                if result >= 0:
                    inserted = True
                    break

                # Reduce gradually until the title fits.
                font_size -= 0.5

            if not inserted:
                raise ValueError(
                    f'Title "{title}" could not fit on one line. '
                    "Try a shorter title or use a wider PDF page."
                )

        # Update PDF metadata.
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
    "customize title size and alignment, rename the files, "
    "and download your generated PDFs."
)

st.info(
    'Your PDF template must contain the searchable text '
    '"Replaced Title Here".'
)

# --------------------------------------------------
# 1. UPLOAD PDF
# --------------------------------------------------

st.subheader("1. Upload PDF Template")

uploaded_pdf = st.file_uploader(
    "Choose your original PDF",
    type=["pdf"],
)

# --------------------------------------------------
# 2. BULK TITLES AND FILENAMES
# --------------------------------------------------

st.subheader("2. Bulk Titles and Rename Strings")

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
        help="Each non-empty line creates one PDF.",
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
            "Each rename string corresponds to the title "
            "on the same line."
        ),
    )

titles = read_lines(titles_input)
rename_strings = read_lines(names_input)

# --------------------------------------------------
# 3. TITLE FORMATTING
# --------------------------------------------------

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
            f"Custom bold font found: "
            f"{Path(font_path).name}"
        )
    else:
        st.warning(
            "Using built-in Helvetica Bold. "
            "For broader Unicode coverage, add a suitable "
            "font to fonts/NotoSans-Bold.ttf."
        )

with size_col:
    size_mode = st.radio(
        "Title size mode",
        ["Preset size", "Custom size"],
        horizontal=True,
    )

    if size_mode == "Preset size":
        title_size = float(
            st.selectbox(
                "Select title size",
                [
                    12, 16, 20, 24, 28, 32, 36,
                    42, 48, 60, 72, 84, 96, 108,
                    120, 144, 160, 180, 200,
                ],
                index=7,
                format_func=lambda size: f"{size} pt",
            )
        )
    else:
        title_size = st.number_input(
            "Custom title size (pt)",
            min_value=5.0,
            max_value=200.0,
            value=60.0,
            step=2.0,
        )

alignment = st.selectbox(
    "Title alignment",
    ["Left", "Center", "Right"],
    index=1,
    help="Choose the horizontal alignment across the page.",
)

st.caption(
    f"Selected size: {title_size:g} pt | "
    f"Alignment: {alignment} | Bold formatting"
)

# --------------------------------------------------
# 4. BATCH SUMMARY
# --------------------------------------------------

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
    "Title size",
    f"{title_size:g} pt",
)

if titles and len(titles) != len(rename_strings):
    st.error(
        "The number of titles and rename strings must match. "
        "Please provide one rename string per title."
    )

if not titles:
    st.caption(
        "Enter at least one title to enable generation."
    )

can_generate = (
    uploaded_pdf is not None
    and len(titles) > 0
    and len(titles) == len(rename_strings)
)

# --------------------------------------------------
# 5. GENERATE PDFS
# --------------------------------------------------

st.subheader("5. Generate PDFs")

if st.button(
    "🚀 Generate PDFs",
    type="primary",
    use_container_width=True,
    disabled=not can_generate,
):
    source_bytes = uploaded_pdf.getvalue()

    generated = []
    failures = []
    used_filenames = set()

    try:
        # Validate the uploaded PDF.
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
                "Please check the PDF template."
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
                    alignment=alignment,
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
        st.error(
            f"Unable to process the batch: {exc}"
        )

# --------------------------------------------------
# 6. RESULTS AND DOWNLOADS
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
        "Each PDF is checked against the 2 MiB size limit. "
        "Oversized PDFs are excluded from the ZIP."
    )

st.divider()

st.caption(
    "Bulk PDF Generator · Python + Streamlit + PyMuPDF"
)
