# Word Error Count

Small utilities for generating word error rate (WER) HTML reports for speech-to-text (STT) outputs.

## What is in this repo

- `highlight_errors.py` highlights insertions, substitutions, and deletions in a single HTML transcript against a ground-truth text file.
- `excel_wer_report.py` builds a multi-sheet HTML dashboard from an Excel workbook.
- `wer_reports/` holds generated report HTML files.

## Requirements

- Python 3.8+
- `pandas`

Install dependencies:

```bash
pip install pandas
```

## Usage

### 1) Highlight a single transcript

```bash
python highlight_errors.py --ref STT_T2_28S_37.txt --hyp STT_T2_28S_37_WER_0.191.html
```

Options:

- `--out` write the highlighted HTML to a specific path
- `--no-deletions` do not insert missing reference words into the output

Output file naming: the script appends or updates a `_WER_###` suffix in the output file name and writes a `.highlighted.html` file.

### 2) Generate a full Excel report

```bash
python excel_wer_report.py --xlsx "EN_UR_Transcription Results.xlsx" --out-dir wer_reports
```

Options:

- `--out` write the full report HTML to a specific path
- `--no-deletions` do not insert missing reference words into the output

The report includes:

- A dashboard to compare WER across sheets and model columns
- Per-sheet sections with row-level highlights

## How WER is computed

WER is calculated as:

$$
WER = \frac{S + I + D}{N}
$$

Where:

- $S$ = substitutions
- $I$ = insertions
- $D$ = deletions
- $N$ = number of reference tokens

## Notes

- The Excel report expects the reference (ground truth) in column C and model outputs in columns D-G.
- Empty rows are skipped.
- HTML outputs are self-contained and can be opened directly in a browser.
