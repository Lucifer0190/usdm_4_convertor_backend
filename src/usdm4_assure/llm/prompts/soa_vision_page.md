You are reading one page image from the Schedule of Activities (SoA) of a clinical trial protocol.
The page's text layer is given below the image instructions; use it for exact spelling, but take the
table STRUCTURE (which cell is in which row and column, which cells are marked) from the image.

Return ONLY a JSON object, no prose, no code fences:

{
  "is_schedule": true,
  "columns": [
    {"visit_number": "<value of a Visit Number row, or empty>", "visit": "<visit label as printed>",
     "epoch": "<period/phase band above it, or empty>", "window": "<visit window as printed, or empty>"}
  ],
  "rows": [
    {"activity": "<row label as printed>", "group": false, "marks": [0, 2]}
  ]
}

Rules:
- "columns" are the VISIT columns only, left to right. Do not include the activity-label column or a
  notes / comments column.
- A visit label is what identifies the column: combine stacked header parts that belong to that one
  column (for example "Cycle 1" over "Day 1" gives "Cycle 1 Day 1"; "Visit Number 2" gives "Visit 2").
  Put windows ("±2 days", "Jul 2022 to Mar 2023") in "window", not in the label.
- If the header has a unit row or band ("Week", "Study Day", "Cycle") over bare numbers, keep the unit
  with the number: "Week 8", never just "8".
- If the header has a row that numbers the visits ("Visit Number: 1, 1a, 2"), put that value in
  "visit_number" and the rest of the column's label (for example "Dose 1") in "visit".
- "epoch" is the merged header cell spanning that column (Screening, Treatment Period, Follow-up...).
- A repeated header on a continuation page is still reported in "columns"; do not report it as a row.
- "rows" are the table body, top to bottom. A heading row with no marks that spans the table
  (for example "CLINICAL ASSESSMENTS") has "group": true and "marks": [].
- "marks" are the 0-based indices into "columns" of cells that are marked (X, checkmark, dot, or a
  short instruction such as "X (every cycle)"). A merged mark spanning several visit columns marks all
  of them. Leave out empty cells and cells holding only a footnote letter.
- Drop footnote letters and asterisks from labels ("EOT a" -> "EOT").
- If the page holds no Schedule of Activities table, return {"is_schedule": false, "columns": [], "rows": []}.

{known_columns}

Text layer of this page:
<<<
{page_text}
>>>
