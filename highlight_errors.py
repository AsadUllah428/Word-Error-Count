import argparse
import html
import os
import re
from html.parser import HTMLParser


class _TextExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = []

    def handle_data(self, data):
        self.parts.append(data)


def _strip_html(raw_html):
    parser = _TextExtractor()
    parser.feed(raw_html)
    return "".join(parser.parts)


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


def _inject_wer_suffix(path, wer_value):
    folder, name = os.path.split(path)
    base, ext = os.path.splitext(name)
    suffix = f"_WER_{wer_value:.3f}"
    if "_WER_" in base:
        base = re.sub(r"_WER_\d+(?:\.\d+)?", suffix, base)
    else:
        base = f"{base}{suffix}"
    return os.path.join(folder, f"{base}{ext}")


def main():
        parser = argparse.ArgumentParser(
                description="Highlight word-level errors in an HTML transcript using a ground truth file."
        )
        parser.add_argument("--ref", required=True, help="Path to the ground truth .txt file")
        parser.add_argument("--hyp", required=True, help="Path to the hypothesis .html file")
        parser.add_argument("--out", help="Path to write highlighted HTML")
        parser.add_argument(
                "--no-deletions",
                action="store_true",
                help="Do not insert missing reference words in the output",
        )
        args = parser.parse_args()

        with open(args.ref, "r", encoding="utf-8") as ref_file:
                ref_text = ref_file.read()

        with open(args.hyp, "r", encoding="utf-8") as hyp_file:
                hyp_html = hyp_file.read()

        hyp_text = _strip_html(hyp_html)

        ref_tokens = _tokenize(ref_text)
        hyp_tokens = _tokenize(hyp_text)

        ops = _align(ref_tokens, hyp_tokens)
        rendered = _render_html(ops, show_deletions=not args.no_deletions)
        subs, ins, dels = _count_errors(ops)
        ref_len = len(ref_tokens)
        wer = (subs + ins + dels) / ref_len if ref_len else 0.0

        output_html = f"""<!doctype html>
<html>
<head>
    <meta charset=\"utf-8\">
    <title>STT Error Highlight</title>
    <style>
        body {{ font-family: "Segoe UI", Tahoma, Geneva, Verdana, sans-serif; line-height: 1.6; }}
        .sub {{ background: #ff4d4f; }}
        .ins {{ background: #fff59d; }}
        .del {{ background: #ff4d4f; text-decoration: line-through; }}
    </style>
</head>
<body>
    <p>
        {rendered}
    </p>
</body>
</html>
"""

        if args.out:
            out_path = _inject_wer_suffix(args.out, wer)
        else:
            hyp_base = os.path.splitext(args.hyp)[0]
            out_path = _inject_wer_suffix(f"{hyp_base}.highlighted.html", wer)

        with open(out_path, "w", encoding="utf-8") as out_file:
            out_file.write(output_html)

        print(f"WER: {wer:.3f}")
        print(f"Output: {out_path}")


if __name__ == "__main__":
    main()
