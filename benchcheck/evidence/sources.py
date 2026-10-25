"""Turn SerpApi responses into evidence records.

A source record carries:
* the Google Scholar result (title, working link, venue line, snippet),
* the best available content and its evidence level — "full text", "abstract",
  or "search snippet" — with the reason for that classification,
* verbatim passages that match each hypothesis's terms (always sliced from the
  retrieved text, never paraphrased),
* the experimental conditions found in the retrieved text and how they compare
  with the user's experiment.
"""

from __future__ import annotations

import hashlib
import re

from ..models import EvidenceContext
from ..reasoning.hypotheses import RULES, Term
from .conditions import (
    applicability,
    compare,
    custom_material_pattern,
    extract_conditions,
    parse_electrolyte,
    user_material_profile,
)
from .text import blocks, collapse_ws, is_verbatim, normalize, sentences

LEVEL_FULL, LEVEL_ABSTRACT, LEVEL_SNIPPET = "full text", "abstract", "search snippet"
FULL_TEXT_MIN_WORDS = 2000
PASSAGE_MAX_CHARS = 480
MIN_PASSAGE_SCORE = 1.0
BODY_SECTIONS = {
    "introduction": "introduction", "experimental": "methods", "experimental section": "methods",
    "experimental methods": "methods", "experimental details": "methods", "experimental procedures": "methods",
    "materials and methods": "methods", "methods": "methods", "methodology": "methods",
    "results": "results", "results and discussion": "results", "discussion": "discussion",
    "conclusion": "conclusion", "conclusions": "conclusion", "summary and conclusions": "conclusion",
}
_HEADING = re.compile(
    r"^[ \t]{0,3}(?:#{1,6}[ \t]*)?(?:\*\*)?(?:\d+(?:\.\d+)*\.?[ \t]+)?"
    r"(introduction|experimental(?: section| methods| details| procedures)?|materials and methods|methods|methodology|"
    r"results(?: and discussion)?|discussion|conclusions?|summary and conclusions|references|"
    r"acknowledge?ments?|abstract|keywords|key words|graphical abstract|highlights|recommended articles|cited by|"
    r"supporting information|supplementary (?:material|information|data)|article info(?:rmation)?|"
    r"author information|funding|data availability)(?:\*\*)?[ \t]*:?[ \t]*$",
    re.IGNORECASE | re.MULTILINE,
)
_SKIP_HOSTS = ("books.google.", "scholar.google.", "google.com/books")

CONTEXT_TERMS = [
    Term("cyclic voltammetry", r"cyclic voltamm|\bCV\b", 1.0),
    Term("redox peaks", r"redox (?:peaks?|couples?)|(?:anodic|cathodic|oxidation|reduction) peaks?", 1.0),
    Term("scan rate", r"scan rates?|sweep rates?", 0.5),
    Term("lithium extraction", r"lithium (?:extraction|recovery)|Li\+? (?:extraction|recovery)", 0.75),
]


def _source_id(result: dict) -> str:
    rid = result.get("result_id")
    if rid:
        return f"gs_{rid}"
    basis = (result.get("title") or "") + "|" + (result.get("link") or "")
    return "src_" + hashlib.sha1(basis.encode("utf-8")).hexdigest()[:12]


def _year_and_venue(summary: str | None) -> tuple[int | None, str | None]:
    if not summary:
        return None, None
    years = re.findall(r"\b(19[5-9]\d|20[0-4]\d)\b", summary)
    parts = [p.strip() for p in summary.split(" - ")]
    venue = None
    if len(parts) >= 2:
        venue = re.sub(r",?\s*\b(19|20)\d{2}\b", "", parts[1]).strip(" ,…") or None
    if len(parts) >= 2 and ("…" in parts[1] or "..." in parts[1]):
        venue = None
    return (int(years[-1]) if years else None), venue


def _usable_url(url: str | None) -> bool:
    return bool(url) and url.startswith(("http://", "https://")) and not any(h in url for h in _SKIP_HOSTS)


def normalize_result(result: dict) -> dict:
    pub = result.get("publication_info") or {}
    year, venue = _year_and_venue(pub.get("summary"))
    links = result.get("inline_links") or {}
    resources = [
        {"title": r.get("title"), "file_format": r.get("file_format"), "link": r.get("link")}
        for r in (result.get("resources") or []) if r.get("link")
    ]
    doi_match = re.search(r"10\.\d{4,9}/[^\s?#]+", result.get("link") or "")
    return {
        "doi": doi_match.group(0) if doi_match else None,
        "source_id": _source_id(result),
        "title": result.get("title") or "(untitled result)",
        "link": result.get("link") if _usable_url(result.get("link")) else None,
        "snippet": result.get("snippet"),
        "publication_summary": pub.get("summary"),
        "authors": [a.get("name") for a in (pub.get("authors") or []) if a.get("name")],
        "year": year,
        "venue": venue,
        "cited_by": ((links.get("cited_by") or {}).get("total")),
        "resources": resources,
        "result_type": result.get("type"),
        "position": result.get("position"),
    }


def _compile_terms(terms: list[Term]):
    out = []
    for t in terms:
        flags = 0 if t.case_sensitive else re.IGNORECASE
        out.append((t, re.compile(t.pattern, flags)))
    return out


def _user_context(ctx: EvidenceContext) -> dict:
    meta = ctx.metadata
    profile = user_material_profile(meta.electrode_material)
    electrolyte = parse_electrolyte(meta.electrolyte or "")
    ref_family = None
    if meta.reference_electrode:
        from ..cv.reference import reference_info

        info = reference_info(meta.reference_electrode)
        ref_family = info["family"] if info else None
    rate = None
    if meta.scan_rate and meta.scan_rate.value:
        rate = meta.scan_rate.value * (1e-3 if (meta.scan_rate.unit or "mV/s").lower().startswith("mv") else 1.0)
    rate = rate or ctx.measured_scan_rate_v_s
    material_patterns = []
    for key in profile["keys"]:
        from .conditions import material_by_key

        mat = material_by_key(key)
        if mat:
            material_patterns += [re.compile(p, re.IGNORECASE if p.islower() else 0) for p in mat.patterns]
    custom = custom_material_pattern(meta.electrode_material)
    if custom:
        material_patterns.append(custom)
    salts = [re.compile(r"(?<![A-Za-z0-9])" + re.escape(s) + r"(?![A-Za-z0-9])") for s in electrolyte["salts"]]
    return {
        "material": profile,
        "analyte": meta.analyte if meta.process_type == "dissolved_species" else None,
        "electrolyte": electrolyte,
        "electrolyte_text": meta.electrolyte,
        "solvent": meta.solvent,
        "reference_family": ref_family,
        "scan_rate_v_s": rate,
        "material_patterns": material_patterns,
        "salt_patterns": salts,
        "custom_material": custom,
    }


def _score_window(text_norm: str, compiled, uctx: dict) -> tuple[float, list[str], bool]:
    score, matched = 0.0, []
    for term, pat in compiled:
        if pat.search(text_norm):
            score += term.weight
            matched.append(term.label)
    hit = bool(matched)
    if any(p.search(text_norm) for p in uctx["material_patterns"]):
        score += 1.0
        matched.append("your material")
    if any(p.search(text_norm) for p in uctx["salt_patterns"]):
        score += 0.5
        matched.append("your electrolyte salt")
    return score, matched, hit


def find_passages(text: str, level: str, location: str, hypothesis_ids: list[str], uctx: dict) -> list[dict]:
    """Best verbatim passage (1–2 sentences) per hypothesis, plus one 'context' passage."""
    if not text:
        return []
    norm = normalize(text)
    windows = []
    # A search snippet is a single excerpt: never split it into heading/body blocks.
    spans = [(0, len(text))] if level == LEVEL_SNIPPET else blocks(text)
    for a, b in spans:
        sents = sentences(text, a, b)
        for k, (s0, s1) in enumerate(sents):
            windows.append((s0, s1))
            if k + 1 < len(sents) and sents[k + 1][1] - s0 <= PASSAGE_MAX_CHARS:
                windows.append((s0, sents[k + 1][1]))
    windows = [(a, b) for a, b in windows if b - a <= PASSAGE_MAX_CHARS * 1.5]
    targets = [(hid, _compile_terms(RULES[hid].terms)) for hid in hypothesis_ids if hid in RULES and RULES[hid].terms]
    targets.append(("context", _compile_terms(CONTEXT_TERMS)))
    out = []
    for hid, compiled in targets:
        best = None
        for a, b in windows:
            score, matched, hit = _score_window(norm[a:b], compiled, uctx)
            if not hit:
                continue
            if hid == "context" and "your material" not in matched and "your electrolyte salt" not in matched:
                continue
            # Prefer shorter windows at equal score.
            key = (score, -(b - a))
            if score >= MIN_PASSAGE_SCORE and (best is None or key > best[0]):
                best = (key, a, b, matched, score)
        if best:
            _, a, b, matched, score = best
            passage = text[a:b].strip()
            shown = collapse_ws(passage)
            out.append({
                "hypothesis_id": hid,
                "text": shown,
                "level": level,
                "location": location,
                "matched_terms": matched,
                "highlights": _highlight_spans(shown, compiled, uctx),
                "score": round(score, 2),
                "verbatim_verified": is_verbatim(passage, text),
                "verification_label": "matches search snippet" if level == LEVEL_SNIPPET else "matches retrieved text",
            })
    return out


def _highlight_spans(shown: str, compiled, uctx: dict) -> list[list[int]]:
    """Character spans of matched terms in the displayed passage (for UI highlighting only)."""
    norm = normalize(shown)
    spans = []
    for pat in [p for _, p in compiled] + uctx["material_patterns"] + uctx["salt_patterns"]:
        for m in pat.finditer(norm):
            a, b = m.start(), m.end()
            while b < len(norm) and norm[b].isalnum():
                b += 1  # extend partial-word matches ("capacity fad" -> "capacity fading")
            if b > a:
                spans.append([a, b])
    spans.sort()
    merged: list[list[int]] = []
    for a, b in spans:
        if merged and a <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], b)
        else:
            merged.append([a, b])
    return merged


def snippet_record(result: dict, ctx: EvidenceContext, query_id: str) -> dict:
    src = normalize_result(result)
    uctx = _user_context(ctx)
    snippet = src["snippet"] or ""
    passages = find_passages(snippet, LEVEL_SNIPPET, "Google Scholar snippet", ctx.hypothesis_ids, uctx)
    extracted = extract_conditions([("title", src["title"]), (LEVEL_SNIPPET, snippet)], uctx["custom_material"], uctx.get("analyte"))
    rows = compare(extracted, uctx)
    src.update({
        "found_by": [query_id],
        "evidence_level": LEVEL_SNIPPET,
        "content": {"status": "snippet only", "reason": "Only the Google Scholar search snippet has been retrieved."},
        "passages": passages,
        "conditions": rows,
        "applicability": applicability(rows),
    })
    return src


# --------------------------------------------------------------------------------------
# Extract API content
# --------------------------------------------------------------------------------------


def _meta_pairs(meta) -> list[tuple[str, str]]:
    pairs = []
    if isinstance(meta, dict):
        for k, v in meta.items():
            if isinstance(v, str):
                pairs.append((k.lower(), v))
            elif isinstance(v, list):
                pairs += [(k.lower(), x) for x in v if isinstance(x, str)]
            elif isinstance(v, dict):
                pairs += [(f"{k}:{kk}".lower(), vv) for kk, vv in v.items() if isinstance(vv, str)]
    elif isinstance(meta, list):
        for item in meta:
            if isinstance(item, dict):
                name = item.get("name") or item.get("property") or item.get("itemprop") or ""
                content = item.get("content") or item.get("value")
                if name and isinstance(content, str):
                    pairs.append((str(name).lower(), content))
    return pairs


def _json_ld_abstracts(data) -> list[str]:
    found = []

    def walk(obj):
        if isinstance(obj, dict):
            for key in ("abstract", "description"):
                if isinstance(obj.get(key), str):
                    found.append(obj[key])
            for v in obj.values():
                walk(v)
        elif isinstance(obj, list):
            for v in obj:
                walk(v)

    walk(data)
    return found


def _section_spans(text: str) -> list[tuple[str, int, int]]:
    heads = [(m.group(1).lower(), m.start(), m.end()) for m in _HEADING.finditer(text)]
    spans = []
    for k, (name, start, end) in enumerate(heads):
        stop = heads[k + 1][1] if k + 1 < len(heads) else len(text)
        spans.append((name, end, stop))
    return spans


def parse_extract(data: dict) -> dict:
    """Interpret an Extract API response defensively (field layout per SerpApi's documentation)."""
    page = data.get("page_information") or {}
    tc = data.get("text_content")
    if isinstance(tc, dict):
        full = tc.get("full") or tc.get("text") or ""
        markdown = tc.get("markdown") or ""
    elif isinstance(tc, str):
        full, markdown = tc, ""
    else:
        full, markdown = "", ""
    text = markdown if len(markdown) > len(full) * 0.6 else full
    text = text or full or markdown
    words = len(re.findall(r"\w+", text))
    title = page.get("title") or data.get("title")

    abstract, abstract_src = None, None
    spans = _section_spans(text)
    for name, a, b in spans:
        if name == "abstract" and len(text[a:b].strip()) >= 300:
            abstract, abstract_src = text[a:b].strip()[:4000], "page text (Abstract section)"
            break
    if abstract is None:
        metas = _meta_pairs(data.get("meta_tags"))
        for key in ("citation_abstract", "dc.description", "dcterms.abstract", "description", "og:description",
                    "twitter:description"):
            vals = [v for k, v in metas if k == key or k.endswith(":" + key)]
            vals = [v for v in vals if len(v) >= 200]
            if vals:
                abstract, abstract_src = max(vals, key=len), f"page metadata ({key})"
                break
    if abstract is None:
        for cand in _json_ld_abstracts(data.get("json_ld")):
            if len(cand) >= 200:
                abstract, abstract_src = cand, "page structured data (JSON-LD)"
                break

    body_found = {BODY_SECTIONS[n] for n, _, _ in spans if n in BODY_SECTIONS}
    body = ""
    if spans:
        first_body = next((a for n, a, _ in spans if n in BODY_SECTIONS), None)
        refs = next((a for n, a, _ in spans if n in ("references", "acknowledgments", "acknowledgements",
                                                         "acknowledgment", "acknowledgement")), None)
        if first_body is not None:
            body = text[first_body:refs if refs and refs > first_body else len(text)]
    if len(body_found) >= 3 and words >= FULL_TEXT_MIN_WORDS:
        level = LEVEL_FULL
        reason = (f"Retrieved page text has {words} words and section headings for "
                  f"{', '.join(sorted(body_found))}; treated as full text (references excluded).")
    elif abstract:
        level = LEVEL_ABSTRACT
        reason = f"Abstract found in {abstract_src}; the full paper text was not available on the retrieved page."
    else:
        level = None
        reason = "The retrieved page had neither an identifiable abstract nor full-text sections."
    return {
        "title": title,
        "final_url": page.get("final_url") or page.get("url") or (data.get("search_parameters") or {}).get("url"),
        "word_count": words,
        "abstract": abstract,
        "abstract_source": abstract_src,
        "body": body,
        "level": level,
        "reason": reason,
        "sections": sorted(body_found),
    }


def extract_record(source: dict, extract_data: dict | None, ctx: EvidenceContext, call_meta: dict) -> dict:
    """Upgrade a snippet-level source record with Extract API content when it is usable."""
    src = dict(source)
    uctx = _user_context(ctx)
    if not extract_data:
        src["content"] = {"status": "retrieval failed", "reason": call_meta.get("error") or "No content returned.",
                          **call_meta}
        return src
    parsed = parse_extract(extract_data)
    metadata = dict(_meta_pairs((extract_data or {}).get("meta_tags")))
    if metadata.get("citation_doi"):
        src["doi"] = metadata["citation_doi"]
    if metadata.get("citation_journal_title"):
        src["venue"] = metadata["citation_journal_title"]
    date = metadata.get("citation_publication_date") or metadata.get("citation_date")
    if date and re.match(r"\d{4}", date):
        src["year"] = int(date[:4])
    content = {"status": parsed["level"] or "no usable content", "reason": parsed["reason"],
               "word_count": parsed["word_count"], "final_url": parsed["final_url"], "sections": parsed["sections"],
               **call_meta}
    src["content"] = content
    src["content"]["ok"] = parsed["level"] is not None
    if parsed["level"] is None:
        return src
    passages = []
    texts = [("title", src.get("title") or "")]
    if parsed["abstract"]:
        passages += find_passages(parsed["abstract"], LEVEL_ABSTRACT, parsed["abstract_source"], ctx.hypothesis_ids, uctx)
        texts.append((LEVEL_ABSTRACT, parsed["abstract"]))
    if parsed["level"] == LEVEL_FULL and parsed["body"]:
        body_passages = find_passages(parsed["body"], LEVEL_FULL, "full text (body, references excluded)",
                                      ctx.hypothesis_ids, uctx)
        have = {p["hypothesis_id"]: p for p in passages}
        for p in body_passages:
            if p["hypothesis_id"] not in have or p["score"] > have[p["hypothesis_id"]]["score"]:
                have[p["hypothesis_id"]] = p
        passages = list(have.values())
        texts.append((LEVEL_FULL, parsed["body"]))
    # Keep snippet passages for hypotheses the richer text did not cover.
    covered = {p["hypothesis_id"] for p in passages}
    passages += [p for p in source.get("passages", []) if p["hypothesis_id"] not in covered]
    texts.append((LEVEL_SNIPPET, source.get("snippet") or ""))
    rows = compare(extract_conditions(texts, uctx["custom_material"], uctx.get("analyte")), uctx)
    src.update({
        "evidence_level": parsed["level"],
        "passages": passages,
        "conditions": rows,
        "applicability": applicability(rows),
    })
    return src


# --------------------------------------------------------------------------------------
# Which sources to spend Extract credits on
# --------------------------------------------------------------------------------------


def extraction_url(source: dict) -> str | None:
    for r in source.get("resources") or []:
        if _usable_url(r.get("link")):
            return r["link"]
    if _usable_url(source.get("link")):
        return source["link"]
    return None


def merge_sources(records: list[dict]) -> list[dict]:
    merged: dict[str, dict] = {}
    for rec in records:
        key = rec["source_id"]
        title_key = re.sub(r"\W+", " ", (rec.get("title") or "").lower()).strip()
        existing = merged.get(key) or next((m for m in merged.values()
                                            if re.sub(r"\W+", " ", (m.get("title") or "").lower()).strip() == title_key), None)
        if existing:
            for q in rec.get("found_by", []):
                if q not in existing["found_by"]:
                    existing["found_by"].append(q)
            existing.setdefault("snippets", [existing.get("snippet")])
            for snippet in rec.get("snippets", [rec.get("snippet")]):
                if snippet and snippet not in existing["snippets"]:
                    existing["snippets"].append(snippet)
            have = {p["text"] for p in existing.get("passages", [])}
            existing["passages"] = existing.get("passages", []) + [p for p in rec.get("passages", [])
                                                                  if p["text"] not in have]
        else:
            merged[key] = {**rec, "found_by": list(rec.get("found_by", []))}
    return list(merged.values())


def select_for_extraction(sources: list[dict], budget: int) -> list[dict]:
    ranked = []
    for s in sources:
        url = extraction_url(s)
        if not url:
            continue
        material = next((r for r in s.get("conditions", []) if r["condition"] == "Electrode material"), {})
        hyp_hits = len({p["hypothesis_id"] for p in s.get("passages", []) if p["hypothesis_id"] != "context"})
        from .serpapi import domain_recently_failed
        key = (
            1 if domain_recently_failed(url) else 0,
            1 if "sciencedirect.com" in url else 0,
            0 if ".pdf" in url.lower() or source_open_access(url) else 1,
            -len(s.get("found_by", [])),
            0 if material.get("status") == "match" else 1 if material.get("status") == "related" else 2,
            -hyp_hits,
            s.get("position") if s.get("position") is not None else 99,
        )
        reason = [f"returned by {len(s.get('found_by', []))} query(ies)"]
        if material.get("status") in ("match", "related"):
            reason.append(f"material {material['status']} in snippet")
        if hyp_hits:
            reason.append(f"snippet matches {hyp_hits} hypothesis term set(s)")
        ranked.append((key, {"source_id": s["source_id"], "url": url, "reason": ", ".join(reason)}))
    ranked.sort(key=lambda x: x[0])
    return [r for _, r in ranked[:budget]]


def source_open_access(url: str) -> bool:
    from urllib.parse import urlsplit
    return (urlsplit(url).hostname or "").lower() in {"arxiv.org", "pmc.ncbi.nlm.nih.gov", "www.mdpi.com", "mdpi.com"}
