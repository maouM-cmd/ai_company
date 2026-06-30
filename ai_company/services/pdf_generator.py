"""
AI生成テキスト → PDF 変換
Windows の Meiryo フォントを使用（日本語対応）
"""
from fpdf import FPDF
from pathlib import Path

FONT_REG = "C:/Windows/Fonts/meiryo.ttc"
FONT_BOLD = "C:/Windows/Fonts/meiryob.ttc"
OUTPUT_DIR = Path(__file__).parent.parent / "gumroad_products"


def generate_pdf(title: str, raw_text: str, output_path: str | None = None) -> bytes:
    """Markdown風テキストをPDFに変換してbytesを返す。output_pathが指定されればファイルにも保存。"""
    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=20)
    pdf.add_page()
    pdf.add_font("Meiryo", "", FONT_REG, uni=True)
    pdf.add_font("Meiryo", "B", FONT_BOLD, uni=True)

    # タイトル
    pdf.set_font("Meiryo", "B", 18)
    pdf.multi_cell(0, 12, title, align="C")
    pdf.ln(8)

    for line in raw_text.split("\n"):
        stripped = line.strip()
        if stripped.startswith("## "):
            pdf.set_font("Meiryo", "B", 14)
            pdf.ln(4)
            pdf.multi_cell(0, 10, stripped[3:])
            pdf.ln(2)
        elif stripped.startswith("### "):
            pdf.set_font("Meiryo", "B", 12)
            pdf.multi_cell(0, 8, stripped[4:])
        elif stripped.startswith("- ") or stripped.startswith("* "):
            pdf.set_font("Meiryo", "", 10)
            pdf.multi_cell(pdf.epw, 7, "  ・" + stripped[2:])
        elif stripped == "---":
            pdf.ln(3)
            pdf.line(10, pdf.get_y(), 200, pdf.get_y())
            pdf.ln(3)
        elif stripped:
            pdf.set_font("Meiryo", "", 10)
            pdf.multi_cell(0, 7, stripped)
        else:
            pdf.ln(4)

    pdf_bytes = pdf.output()

    if output_path:
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        Path(output_path).write_bytes(pdf_bytes)

    return pdf_bytes


def save_product_pdf(product_type: str, title: str, raw_text: str) -> Path:
    """商品PDFをgumroad_productsディレクトリに保存してパスを返す"""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    safe_name = product_type.replace("/", "_").replace(" ", "_")
    out_path = OUTPUT_DIR / f"{safe_name}.pdf"
    generate_pdf(title, raw_text, str(out_path))
    return out_path
