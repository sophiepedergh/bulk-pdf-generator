import io
import re
import zipfile
from pathlib import Path

import fitz  # PyMuPDF
import streamlit as st

MAX_SIZE = 2 * 1024 * 1024  # 2.0 MiB
PLACEHOLDER = "Replaced Title Here"
FONT_DIR = Path(__file__).parent / "fonts"

st.set_page_config(
    page_title="Bulk PDF Generator",
    page_icon="📄",
    layout="wide",
)

st.title("📄 Bulk PDF Generator")
st.caption(
    "Upload a PDF, replace its title in bulk, "
    "optimize the files, and download a ZIP."
)


def read_lines(text):
    """Read one non-empty value per line."""
    return [line.strip() for line in text.splitlines() if line.strip()]


def safe_filename(value):
    """Remove characters that are unsafe in common filenames."""
    value = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", value)
    value = value.strip().rstrip(".")
    return value[:180] or "document"


def unique_filename(name, used):
    """Prevent duplicate filenames inside the ZIP."""
    base = safe_filename(name)
    candidate = base
    counter = 2

    while candidate.casefold() in used:
        candidate = f"{base}_{counter}"
        counter += 1

    used.add(candidate.casefold())
    return candidate + ".pdf"


def find_font():
    """Find an optional bundled bold font."""
    candidates = [
        FONT_DIR / "NotoSans-Bold.ttf",
        FONT_DIR / "DejaVuSans-Bold.ttf",
    ]
    for path in candidates:
        if path.is_file():
            return str(path)
    return None


def create_pdf(source_bytes, title, font_path=None):
    """
    Replace every searchable placeholder occurrence.
    The replacement is bold when a suitable font is available.
    """
    doc = fitz.open(stream=source_bytes, filetype="pdf")

    try:
        found = []

        for page_number, page in enumerate(doc):
            for rect in page.search_for(PLACEHOLDER):
                found.append((page_number, rect))

        if not found:
            raise ValueError(
                f'Could not find "{PLACEHOLDER}" in searchable PDF text. '
                "The placeholder may be an image or outlined text."
            )

        # Redact all occurrences before inserting replacements.
        for page_number, rect in found:
            page = doc[page_number]
            page.add_redact_annot(
                rect,
                fill=(1, 1, 1),
                cross_out=False,
            )

        for page in doc:
            page.apply_redactions(images=0, graphics=0)

        # Insert the replacement in the original placeholder area.
        for page_number, original_rect in found:
            page = doc[page_number]

            # Keep the same line area and avoid crossing the page edge.
            rect = fitz.Rect(original_rect)
            rect.x1 = min(page.rect.x1 - 24, max(
                rect.x1, rect.x0 + 20
            ))

            font_size = max(5.0, min(24.0, rect.height * 0.78))
            inserted = False

            while font_size >= 5.0:
                kwargs = {
                    "fontsize": font_size,
                    "align": fitz.TEXT_ALIGN_LEFT,
                    "overlay": True,
                }

                if font_path:
                    kwargs["fontfile"] = font_path
                    kwargs["fontname"] = "CustomBold"

                result = page.insert_textbox(
                    rect,
                    title,
                    **kwargs,
                )

                # PyMuPDF returns a non-negative value on success.
                if result >= 0:
                    inserted = True
                    break

                font_size -= 0.5

            if not inserted:
                raise ValueError(
                    f'Title "{title}" does not fit in the '
                    "placeholder area. Use a shorter title or "
                    "adjust the template layout."
                )

        # Set PDF document metadata.
        metadata = doc.metadata
        metadata["title"] = title
        doc.set_metadata(metadata)

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


# ---------------- Streamlit interface ----------------

uploaded_pdf = st.file_uploader(
    "1. Upload your PDF template",
    type=["pdf"],
)

st.info(
    'Your PDF should contain searchable text reading '
    '"Replaced Title Here".'
)

col1, col2 = st.columns(2)

with col1:
    titles_input = st.text_area(
        "2. Bulk titles — one per line",
        height=260,
        placeholder=(
            "Stream\n"
            "𝐒𝐭𝐫𝐞𝐚𝐦\n"
            "Ｓｔｒｅａｍｉｎｇ"
        ),
    )

with col2:
    names_input = st.text_area(
        "3. Bulk rename strings — one per line",
        height=260,
        placeholder=(
            "stream-document\n"
            "bold-stream-document\n"
            "streaming-document"
        ),
    )

font_path = find_font()

with st.expander("Font and formatting settings"):
    st.write(
        "A bundled font can improve bold formatting and "
        "Unicode coverage. Add a suitable TTF font to "
        "the fonts/ directory in your GitHub repository."
    )
    st.write(
        "Unicode characters are retained in the title string, "
        "but exact visual appearance depends on the font's glyph "
        "coverage. A font cannot reproduce every Unicode style."
    )

titles = read_lines(titles_input)
names = read_lines(names_input)

st.write(f"**Titles:** {len(titles)}")
st.write(f"**Rename strings:** {len(names)}")

if titles and names and len(titles) != len(names):
    st.warning(
        "The number of titles and rename strings must match. "
        "Each line is paired by its position."
    )

if titles and names and len(titles) == len(names):
    st.caption(
        f"{len(titles)} PDF files will be generated."
    )

if st.button(
    "Generate PDFs",
    type="primary",
    use_container_width=True,
    disabled=not (
        uploaded_pdf
        and titles
        and names
        and len(titles) == len(names)
    ),
):
    try:
        source_bytes = uploaded_pdf.getvalue()

        # Validate the template before starting a batch.
        with fitz.open(
            stream=source_bytes,
            filetype="pdf",
        ) as check_doc:
            if check_doc.needs_pass:
                st.error(
                    "The PDF is password-protected. "
                    "Upload an unlocked PDF."
                )
                st.stop()

        generated = []
        failures = []
        used_names = set()
        progress = st.progress(0)
        status = st.empty()

        for index, (title, rename) in enumerate(
            zip(titles, names), start=1
        ):
            status.write(
                f"Processing {index}/{len(titles)}: {title}"
            )

            try:
                pdf_bytes = create_pdf(
                    source_bytes,
                    title,
                    font_path,
                )

                # Reject oversized files instead of pretending
                # they satisfy the size limit.
                if len(pdf_bytes) > MAX_SIZE:
                    failures.append({
                        "title": title,
                        "filename": rename,
                        "reason": (
                            f"File is {len(pdf_bytes) / 1024 / 1024:.2f} "
                            "MiB after optimization; limit is 2.0 MiB."
                        ),
                    })
                else:
                    filename = unique_filename(
                        rename, used_names
                    )
                    generated.append(
                        (filename, pdf_bytes, title)
                    )

            except Exception as exc:
                failures.append({
                    "title": title,
                    "filename": rename,
                    "reason": str(exc),
                })

            progress.progress(index / len(titles))

        status.empty()
        progress.empty()

        st.session_state["generated_pdfs"] = generated
        st.session_state["pdf_failures"] = failures

    except Exception as exc:
        st.error(f"Unable to process the PDF: {exc}")


generated = st.session_state.get("generated_pdfs", [])
failures = st.session_state.get("pdf_failures", [])

if generated or failures:
    st.divider()
    st.subheader("Generation results")

    good, bad = st.columns(2)
    good.metric("Successful PDFs", len(generated))
    bad.metric("Failed or oversized", len(failures))

    if generated:
        zip_buffer = io.BytesIO()

        with zipfile.ZipFile(
            zip_buffer,
            mode="w",
            compression=zipfile.ZIP_DEFLATED,
        ) as archive:
            for filename, pdf_bytes, title in generated:
                archive.writestr(filename, pdf_bytes)

        st.download_button(
            "⬇️ Download all PDFs (ZIP)",
            data=zip_buffer.getvalue(),
            file_name="bulk_generated_pdfs.zip",
            mime="application/zip",
            use_container_width=True,
        )

        with st.expander("View successful files"):
            for filename, pdf_bytes, title in generated:
                size_mb = len(pdf_bytes) / (1024 * 1024)
                st.write(
                    f"✅ **{filename}** — "
                    f"{size_mb:.3f} MiB — {title}"
                )

        # Optional individual PDF downloads.
        with st.expander("Download individual PDFs"):
            for filename, pdf_bytes, title in generated:
                st.download_button(
                    f"Download {filename}",
                    data=pdf_bytes,
                    file_name=filename,
                    mime="application/pdf",
                    key=f"download_{filename}",
                )

    if failures:
        with st.expander("View failed files"):
            for item in failures:
                st.error(
                    f"{item['filename']} — {item['title']}: "
                    f"{item['reason']}"
                )
