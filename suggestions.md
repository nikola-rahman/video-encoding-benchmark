# Report Review — Suggestions

Review of `report/output/latest/report.md` (v0.1, 2026-05-10).

The framing, methodology, and headline tables are well-conceived. The benchmark measures what it claims to measure (smallest file at a target VMAF), and where Vidaio wins on that task, the report should say so — that is its job. The issues below are about gaps, internal consistency, and metric robustness, not about manufacturing balance.

Items are grouped by severity. Each one is independent — pick what's worth fixing for v1.0.

---

## Must change

1. **§9 Conclusions is a placeholder** — currently `*To be written after data analysis.*`. Either write it or don't ship. The Executive Summary cannot be the only synthesis.

2. **§1 headline findings #3 and #4 are placeholders.** "AV1 delivers 49% better compression than H.265" is followed by `*To be computed from full results.*`, and #4 is similarly vague. Don't put unfilled bullets next to fully-filled ones in the headlines — it undermines the two real findings sitting alongside.

3. **§4 results-by-codec subsections are empty.** 4.1.3 / 4.1.4 / 4.1.5 / 4.1.6 / 4.2.3 / 4.2.4 / 4.2.5 / 4.2.6 are figure references with no commentary. Per-vertical analysis is what a buyer skims to. Right now the figures are the analysis, and figures don't say what to take away.

4. **Appendix B "Exact Encoding Configuration" is `Configuration to be documented.` for all four providers.** For an independent benchmark, this is the load-bearing reproducibility section. Without it the methodology is unverifiable.

5. **Appendix D source provenance is all `TBD`.** SHA-256, source URL, license, frame count are blank. For UGC and archive content, license/source matters legally and methodologically.

6. **§3.2 says "AV1 TODO" for AWS, Bitmovin, Zencoder — but §4.1 reports AV1 results for AWS and Bitmovin.** Stale TODOs in a methodology table contradict the data section.

7. **The 798% / 5.5 MB vs 30 MB / 447% headline numbers don't reconcile with the BD-Rate table** (worst gap there is +43% H.265, +273.6% AV1). They're computed on different bases. Either pick one framing or explain the relationship explicitly. A careful reader will notice and start distrusting other numbers.

---

## Should change

8. **"Average compression ratio" is a noisy aggregate.** Compression ratio is `input / output`; averaging ratios across clips of wildly different complexity yields a number dominated by the easiest clips. Vidaio's AV1 ratios on `security_virat_*` hit 100×–272× because static surveillance footage at VMAF 85 compresses extremely well — those values dominate the mean. Use geometric mean, or report per-vertical breakdowns, or weight by source bytes. This is a metric-quality concern (true for every provider), not a bias concern.

9. **The catastrophic VMAF-min failures are invisible in the body.** `ugc_surprise_reaction` shows VMAF min ≈ 5.8–6.0 across Vidaio AV1, Vidaio H.265, *and* Bitmovin H.265 — likely a black/transition frame all encoders mishandle. §3.3 explicitly motivates percentiles ("Why percentiles matter"); then the body uses only means. Either explain the failure mode or surface it as a finding.

10. **"Effective cost per source minute" needs one extra caveat sentence.** The metric is correct for the benchmark's stated task (achieving a target VMAF), but as written it could be misread as generic pricing — Bitmovin does not charge $2.42/min for AV1 in normal use. Add: *"this reflects the cost to achieve a target VMAF via iterative search; providers without native VMAF targeting incur this search overhead, which a customer running a fixed CRF/QVBR setting would not pay."*

11. **§5 Storage Efficiency is one paragraph and one figure.** For a report whose stated audience is storage-cost buyers, this section deserves more. At minimum: numerical totals per provider, and a sentence on what a 447% file-size gap means for a representative annual S3 spend.

12. **§1 BD-Rate column reads oddly alongside avg VMAF.** Vidaio is rank 1 on H.265 with avg VMAF 88.7 — the lowest in the table. BD-Rate at matched quality is the right metric, but readers will scan VMAF and conclude "Vidaio is worst on quality." Add a one-line footnote: *BD-Rate is computed on the overlapping VMAF range, not on raw averages — providers may target different quality levels by default.*

---

## Could change

13. **Reorder §8 and §9.** Convention is Conclusions → Limitations. Limitations before conclusions reads like an apology for findings the reader hasn't seen yet.

14. **"Headline findings" + "Headline findings tables"** is redundant phrasing. Merge into one section with bullets and tables interleaved, or rename the second to "Aggregate Results."

15. **`(45 (clip, target) combos)`** — nested parens. "across 45 clip × target combinations" reads cleaner.

16. **§2 ends abruptly** after the streaming/single-file paragraph. A one-line closer tying it to §3 (e.g. "...therefore this benchmark targets single-file efficiency at matched VMAF") would help.

17. **§3.1 SI/TI table is dense.** Consider a short prose summary ("test corpus spans SI 47-116 and TI 1.6-23.2; security clips cluster low-TI, UGC clusters high-TI") and put the full table in an appendix.

---

## What's good

- **Opening framing is strong.** "Existing benchmarks evaluate streaming; nobody benchmarks single-file" is a real, defensible gap. The Mux/Cloudflare exclusion paragraph up front builds trust.
- **§3.3 is solid methodology writing.** VMAF model named, percentile reasoning given, BD-Rate construction explained, why-Vidaio-dictates-the-metric is honestly disclosed.
- **§7 encoding-speed caveat is well-judged.** Explicitly says "this is end-to-end wall-clock, not encoder speed, and not isolatable from outside a cloud API." Right epistemic posture — clone it into more sections.
- **§6 pricing is dated, sourced, and shows the multiplier math.** Concrete and citable.
- **§3.2 fairness statement** ("smallest possible file at given target quality") gives the reader a clear lens for everything that follows.
- **Limitations list is substantive**, not boilerplate. The VMAF-on-UGC and provider-evolution caveats are real.

---

## Meta

The report calls itself v0.1, which is honest, but it also presents as a published deliverable (PDF rendering, "Author / Commissioned by / Date" header, "Draft results were shared with all tested providers") while having `TBD`s in the appendix and an empty Conclusions section. Pick a lane: either label it "preliminary draft, not for distribution" prominently, or finish the empty sections before circulating.

Two days of writing on §4 + §9, plus filling Appendices B and D and adding the labeling fixes in §10 / §12, would move this from "draft" to "report I'd cite."
