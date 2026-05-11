import argparse
import html
import os
import re

import pandas as pd


def _normalize_token(token):
    norm = re.sub(r"^\W+|\W+$", "", token.lower())
    return norm if norm else token.lower()


def _tokenize(text):
    cleaned = re.sub(r"\s+", " ", text).strip()
    return cleaned.split() if cleaned else []


def _align(ref_tokens, hyp_tokens):
    ref_norm = [_normalize_token(t) for t in ref_tokens]
    hyp_norm = [_normalize_token(t) for t in hyp_tokens]

    m = len(ref_tokens)
    n = len(hyp_tokens)
    dp = [[0] * (n + 1) for _ in range(m + 1)]
    back = [[""] * (n + 1) for _ in range(m + 1)]

    for i in range(1, m + 1):
        dp[i][0] = i
        back[i][0] = "del"
    for j in range(1, n + 1):
        dp[0][j] = j
        back[0][j] = "ins"

    for i in range(1, m + 1):
        for j in range(1, n + 1):
            if ref_norm[i - 1] == hyp_norm[j - 1]:
                best = dp[i - 1][j - 1]
                op = "eq"
            else:
                best = dp[i - 1][j - 1] + 1
                op = "sub"

            ins = dp[i][j - 1] + 1
            if ins < best:
                best = ins
                op = "ins"

            delete = dp[i - 1][j] + 1
            if delete < best:
                best = delete
                op = "del"

            dp[i][j] = best
            back[i][j] = op

    ops = []
    i = m
    j = n
    while i > 0 or j > 0:
        op = back[i][j]
        if op == "eq":
            ops.append(("eq", ref_tokens[i - 1], hyp_tokens[j - 1]))
            i -= 1
            j -= 1
        elif op == "sub":
            ops.append(("sub", ref_tokens[i - 1], hyp_tokens[j - 1]))
            i -= 1
            j -= 1
        elif op == "ins":
            ops.append(("ins", "", hyp_tokens[j - 1]))
            j -= 1
        else:
            ops.append(("del", ref_tokens[i - 1], ""))
            i -= 1

    ops.reverse()
    return ops


def _render_html(ops, show_deletions):
    parts = []
    for op, ref_tok, hyp_tok in ops:
        if op == "eq":
            parts.append(html.escape(hyp_tok))
        elif op == "sub":
            expected = html.escape(ref_tok)
            actual = html.escape(hyp_tok)
            parts.append(
                f'<span class="sub" title="expected: {expected}">{actual}</span>'
            )
        elif op == "ins":
            actual = html.escape(hyp_tok)
            parts.append(f'<span class="ins" title="extra">{actual}</span>')
        elif op == "del" and show_deletions:
            expected = html.escape(ref_tok)
            parts.append(
                f'<span class="del" title="missing">{expected}</span>'
            )

    return " ".join(parts)


def _count_errors(ops):
    subs = sum(1 for op, _, __ in ops if op == "sub")
    ins = sum(1 for op, _, __ in ops if op == "ins")
    dels = sum(1 for op, _, __ in ops if op == "del")
    return subs, ins, dels


def _safe_text(value):
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    text = str(value).strip()
    return text


def _slugify(text):
    slug = re.sub(r"[^A-Za-z0-9._-]+", "_", text).strip("_")
    return slug or "sheet"


def _build_sheet_section(sheet_name, sheet_id, ref_items_html, columns_html, wer_summary):
        summary_html = "".join(
                f"<div class=\"summary-item\">{html.escape(label)}: <strong>{wer:.3f}</strong></div>"
                for label, wer in wer_summary
        )

        return f"""
<section class=\"sheet\" data-sheet=\"{html.escape(sheet_id)}\">
    <div class=\"sheet-header\">
        <h2>{html.escape(sheet_name)}</h2>
    </div>
    <div class=\"summary\">{summary_html}</div>
    <div class=\"ref-block\">
        <h3>Reference (ground truth)</h3>
        <div class=\"ref-list\">
            {"".join(ref_items_html)}
        </div>
    </div>
    <div class=\"columns\">
        {"".join(columns_html)}
    </div>
</section>
"""


def _build_dashboard_section(dashboard_headers, dashboard_rows):
        header_cells = "".join(
                f"<th>{html.escape(label)}</th>" for label in dashboard_headers
        )
        rows_html = []
        for sheet_name, sheet_id, wer_map in dashboard_rows:
                cells = "".join(
                        f"<td>{wer_map.get(label, 0.0):.3f}</td>" if label in wer_map else "<td>-</td>"
                        for label in dashboard_headers
                )
                rows_html.append(
                        """
<tr>
    <td class=\"sheet-name\">{name}</td>
    {cells}
    <td class=\"sheet-action\"><button class=\"mini-button\" data-target=\"{sheet_id}\" type=\"button\">Open</button></td>
</tr>
""".format(
                                name=html.escape(sheet_name),
                                cells=cells,
                                sheet_id=html.escape(sheet_id),
                        )
                )

        averages = []
        for label in dashboard_headers:
                values = [row[2][label] for row in dashboard_rows if label in row[2]]
                avg = sum(values) / len(values) if values else 0.0
                averages.append((label, avg))

        avg_items = "".join(
                f"<div class=\"summary-item\">{html.escape(label)} avg: <strong>{avg:.3f}</strong></div>"
                for label, avg in averages
        )

        return f"""
<section class=\"sheet dashboard\" data-sheet=\"dashboard\">
    <div class=\"sheet-header\">
        <h2>Dashboard</h2>
        <p class=\"subtitle\">Compare WER across all sheets and models.</p>
    </div>
    <div class=\"summary\">{avg_items}</div>
    <div class=\"table-wrap\">
        <table class=\"dashboard-table\">
            <thead>
                <tr>
                    <th>Sheet</th>
                    {header_cells}
                    <th>View</th>
                </tr>
            </thead>
            <tbody>
                {"".join(rows_html)}
            </tbody>
        </table>
    </div>
</section>
"""


def _build_page_html(sheet_options_html, sheet_buttons_html, dashboard_html, sections_html):
    return f"""<!doctype html>
<html>
<head>
    <meta charset=\"utf-8\">
    <title>WER Report</title>
    <style>
        :root {{
            --ink: #1f2933;
            --muted: #5f6b76;
            --line: #e1e5ea;
            --panel: #ffffff;
            --accent: #2f6fed;
            --accent-dark: #1f4fbf;
            --bg: #f3f6fb;
        }}
        * {{ box-sizing: border-box; }}
        body {{
            font-family: "Segoe UI", Tahoma, Geneva, Verdana, sans-serif;
            line-height: 1.5;
            margin: 0;
            color: var(--ink);
            background: var(--bg);
        }}
        .page {{ max-width: none; margin: 0; padding: 24px; }}
        h1 {{ margin: 0 0 6px; font-size: 28px; }}
        h2 {{ margin: 0 0 8px; }}
        h3 {{ margin: 0 0 8px; }}
        .subtitle {{ margin: 0; color: var(--muted); }}
        .header {{
            padding: 18px 20px;
            border-radius: 16px;
            border: 1px solid var(--line);
            background: linear-gradient(135deg, #fff4dc 0%, #edf2ff 100%);
            box-shadow: 0 10px 24px rgba(20, 30, 60, 0.08);
        }}
        .toolbar {{
            display: flex;
            flex-wrap: wrap;
            align-items: center;
            gap: 12px;
            margin: 16px 0 18px;
        }}
        .select-wrap {{ position: relative; min-width: 220px; }}
        .select-wrap select {{
            width: 100%;
            appearance: none;
            border: 1px solid var(--line);
            border-radius: 10px;
            padding: 10px 36px 10px 12px;
            background: #fff;
            font-size: 14px;
        }}
        .select-wrap::after {{
            content: "v";
            position: absolute;
            right: 12px;
            top: 50%;
            transform: translateY(-50%);
            color: var(--muted);
            pointer-events: none;
        }}
        .tabs {{
            display: flex;
            gap: 8px;
            flex-wrap: wrap;
        }}
        .tab-button {{
            border: 1px solid var(--line);
            background: #fff;
            color: var(--ink);
            border-radius: 999px;
            padding: 8px 14px;
            font-size: 13px;
            cursor: pointer;
            transition: all 0.2s ease;
        }}
        .tab-button:hover {{ border-color: var(--accent); color: var(--accent); }}
        .tab-button.active {{ background: var(--accent); color: #fff; border-color: var(--accent); }}
        .legend {{
            display: flex;
            flex-wrap: wrap;
            gap: 10px 16px;
            padding: 10px 12px;
            background: #fff;
            border: 1px solid var(--line);
            border-radius: 10px;
        }}
        .legend span {{ display: inline-flex; align-items: center; gap: 6px; font-size: 13px; }}
        .swatch {{ width: 16px; height: 16px; display: inline-block; border-radius: 3px; }}
        .summary {{
            display: flex;
            flex-wrap: wrap;
            gap: 12px 20px;
            margin: 12px 0 20px;
            padding: 10px 12px;
            background: #fff;
            border: 1px solid var(--line);
            border-radius: 10px;
        }}
        .summary-item strong {{ font-weight: 700; }}
        .sheet-header {{ display: flex; align-items: baseline; gap: 12px; }}
        .ref-block {{
            margin: 16px 0 24px;
            padding: 12px;
            border: 1px solid var(--line);
            border-radius: 10px;
            background: #fff;
        }}
        .ref-block h3 {{ margin: 0 0 12px; font-size: 16px; }}
        .ref-item {{
            padding: 6px 0;
            border-bottom: 1px dashed #e8e8e8;
        }}
        .ref-item:last-child {{ border-bottom: none; }}
        .row-meta {{ font-size: 12px; color: var(--muted); margin-bottom: 4px; }}
        .ref-text {{ font-size: 13px; color: #444; }}
        .columns {{
            display: grid;
            grid-template-columns: repeat(4, minmax(0, 1fr));
            gap: 16px;
        }}
        .col {{
            border: 1px solid var(--line);
            border-radius: 12px;
            padding: 12px;
            background: #fff;
            min-width: 0;
        }}
        .col h3 {{
            margin: 0 0 12px;
            font-size: 15px;
            border-bottom: 1px solid #eee;
            padding-bottom: 6px;
        }}
        .item {{
            padding: 8px 0;
            border-bottom: 1px dashed #e8e8e8;
        }}
        .item:last-child {{ border-bottom: none; }}
        .hyp {{ font-size: 14px; }}
        .sub {{ background: #ff4d4f; }}
        .ins {{ background: #fff59d; }}
        .del {{ background: #ff4d4f; text-decoration: line-through; }}
        .sheet {{ display: none; margin-top: 18px; }}
        .sheet.active {{ display: block; }}
        .table-wrap {{ overflow-x: auto; border-radius: 12px; border: 1px solid var(--line); background: #fff; }}
        .dashboard-table {{ width: 100%; border-collapse: collapse; min-width: 640px; }}
        .dashboard-table th, .dashboard-table td {{ padding: 10px 12px; border-bottom: 1px solid #f0f0f0; text-align: left; }}
        .dashboard-table thead th {{ background: #f8fafc; font-weight: 600; }}
        .dashboard-table tbody tr:hover {{ background: #f9fbff; }}
        .sheet-name {{ font-weight: 600; }}
        .mini-button {{
            border: 1px solid var(--accent);
            color: var(--accent);
            background: #fff;
            border-radius: 999px;
            padding: 6px 12px;
            font-size: 12px;
            cursor: pointer;
        }}
        .mini-button:hover {{ background: var(--accent); color: #fff; }}
        @media (max-width: 1200px) {{
            .columns {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }}
        }}
        @media (max-width: 700px) {{
            .columns {{ grid-template-columns: 1fr; }}
            .toolbar {{ flex-direction: column; align-items: stretch; }}
        }}
    </style>
</head>
<body>
    <div class=\"page\">
        <div class=\"header\">
            <h1>WER Report</h1>
            <p class=\"subtitle\">Review speech-to-text quality across all sheets and models.</p>
            <div class=\"toolbar\">
                <div class=\"select-wrap\">
                    <select id=\"sheetSelect\">
                        {sheet_options_html}
                    </select>
                </div>
                <div class=\"tabs\">
                    {sheet_buttons_html}
                </div>
            </div>
            <div class=\"legend\">
                <span><i class=\"swatch\" style=\"background:#fff59d;\"></i>Yellow = insertion (extra word)</span>
                <span><i class=\"swatch\" style=\"background:#ff4d4f;\"></i>Red = substitution (wrong word)</span>
                <span><i class=\"swatch\" style=\"background:#ff4d4f; text-decoration: line-through;\"></i>Strikethrough = deletion (missing word)</span>
            </div>
        </div>
        {dashboard_html}
        {"".join(sections_html)}
    </div>
    <script>
        const select = document.getElementById('sheetSelect');
        const sections = Array.from(document.querySelectorAll('.sheet'));
        const buttons = Array.from(document.querySelectorAll('.tab-button'));
        const miniButtons = Array.from(document.querySelectorAll('.mini-button'));

        function showSheet(id) {{
            sections.forEach(section => {{
                section.classList.toggle('active', section.dataset.sheet === id);
            }});
            buttons.forEach(button => {{
                button.classList.toggle('active', button.dataset.target === id);
            }});
            if (select.value !== id) {{
                select.value = id;
            }}
        }}

        buttons.forEach(button => {{
            button.addEventListener('click', () => showSheet(button.dataset.target));
        }});
        miniButtons.forEach(button => {{
            button.addEventListener('click', () => showSheet(button.dataset.target));
        }});
        select.addEventListener('change', (e) => showSheet(e.target.value));

        if (select.options.length > 0) {{
            showSheet(select.value);
        }}
    </script>
</body>
</html>
"""


def main():
    parser = argparse.ArgumentParser(
        description="Generate WER-highlighted HTML reports from an Excel file."
    )
    parser.add_argument(
        "--xlsx",
        required=True,
        help="Path to the Excel file (e.g., EN_UR_Transcription Results.xlsx)",
    )
    parser.add_argument(
        "--out-dir",
        default="wer_reports",
        help="Output directory for the HTML report",
    )
    parser.add_argument(
        "--out",
        default=None,
        help="Output HTML file path (default: <out-dir>/wer_report.html)",
    )
    parser.add_argument(
        "--no-deletions",
        action="store_true",
        help="Do not insert missing reference words in the output",
    )
    args = parser.parse_args()

    sheets = pd.read_excel(args.xlsx, sheet_name=None)
    os.makedirs(args.out_dir, exist_ok=True)

    sections_html = []
    sheet_options = ["<option value=\"dashboard\" selected>Dashboard</option>"]
    sheet_buttons = [
        "<button class=\"tab-button\" data-target=\"dashboard\" type=\"button\">Dashboard</button>"
    ]
    dashboard_rows = []
    default_labels = {
        3: "Column D",
        4: "Column E",
        5: "Column F",
        6: "Column G",
    }
    global_labels = {}
    pred_indices = [3, 4, 5, 6]

    for sheet_index, (sheet_name, df) in enumerate(sheets.items(), start=1):
        if df.empty or df.shape[1] < 4:
            continue

        display_name = f"Sheet {sheet_index}"

        ref_idx = 2  # Column C
        available_pred_indices = [idx for idx in pred_indices if idx < df.shape[1]]
        if not available_pred_indices:
            continue

        columns_html = []
        wer_summary = []
        rows_data = []

        for row_idx, row in df.iterrows():
            ref_text = _safe_text(row.iloc[ref_idx])
            hyp_texts = []
            has_data = bool(ref_text)

            for pred_idx in available_pred_indices:
                hyp_text = _safe_text(row.iloc[pred_idx])
                hyp_texts.append(hyp_text)
                if hyp_text:
                    has_data = True

            if not has_data:
                continue

            rows_data.append(
                {
                    "row_number": row_idx + 2,
                    "ref_text": ref_text,
                    "ref_tokens": _tokenize(ref_text),
                    "hyp_texts": hyp_texts,
                }
            )

        if not rows_data:
            continue

        ref_items_html = []
        for row_data in rows_data:
            ref_items_html.append(
                """
<div class=\"ref-item\">
  <div class=\"row-meta\">Row {row}</div>
  <div class=\"ref-text\">{ref}</div>
</div>
""".format(
                    row=row_data["row_number"],
                    ref=html.escape(row_data["ref_text"]),
                )
            )

        for col_pos, col_idx in enumerate(available_pred_indices):
            label_candidate = (
                str(df.columns[col_idx]) if col_idx < len(df.columns) else ""
            ).strip()
            if not label_candidate or label_candidate.lower().startswith("unnamed"):
                label_candidate = default_labels.get(col_idx, f"Column {col_idx + 1}")
            if col_idx not in global_labels:
                global_labels[col_idx] = label_candidate
            col_label = global_labels[col_idx]
            total_errors = 0
            total_ref = 0
            items_html = []

            for row_data in rows_data:
                ref_tokens = row_data["ref_tokens"]
                hyp_text = row_data["hyp_texts"][col_pos]
                hyp_tokens = _tokenize(hyp_text)
                ops = _align(ref_tokens, hyp_tokens)

                if ref_tokens:
                    subs, ins, dels = _count_errors(ops)
                    total_errors += subs + ins + dels
                    total_ref += len(ref_tokens)

                rendered = _render_html(ops, show_deletions=not args.no_deletions)
                items_html.append(
                    """
<div class=\"item\">
  <div class=\"row-meta\">Row {row}</div>
  <div class=\"hyp\">{hyp}</div>
</div>
""".format(
                        row=row_data["row_number"],
                        hyp=rendered,
                    )
                )

            wer = (total_errors / total_ref) if total_ref else 0.0
            wer_summary.append((col_label, wer))
            columns_html.append(
                """
<div class=\"col\">
  <h3>{label} (WER: {wer:.3f})</h3>
  {items}
</div>
""".format(
                    label=html.escape(col_label),
                    wer=wer,
                    items="".join(items_html) if items_html else "<em>No data</em>",
                )
            )

        if not columns_html:
            continue

        sheet_id = f"sheet_{sheet_index}"
        sheet_options.append(
            f"<option value=\"{html.escape(sheet_id)}\">{html.escape(display_name)}</option>"
        )
        sheet_buttons.append(
            f"<button class=\"tab-button\" data-target=\"{html.escape(sheet_id)}\" type=\"button\">{html.escape(display_name)}</button>"
        )
        sections_html.append(
            _build_sheet_section(display_name, sheet_id, ref_items_html, columns_html, wer_summary)
        )
        dashboard_rows.append((display_name, sheet_id, dict(wer_summary)))

    if not sections_html:
        print("No report content generated.")
        return

    dashboard_headers = [
        global_labels[idx] for idx in pred_indices if idx in global_labels
    ]
    dashboard_html = _build_dashboard_section(dashboard_headers, dashboard_rows)

    os.makedirs(args.out_dir, exist_ok=True)
    out_path = args.out or os.path.join(args.out_dir, "wer_report.html")
    page_html = _build_page_html(
        "".join(sheet_options),
        "".join(sheet_buttons),
        dashboard_html,
        sections_html,
    )

    with open(out_path, "w", encoding="utf-8") as handle:
        handle.write(page_html)

    print(f"Report written to: {out_path}")


if __name__ == "__main__":
    main()
