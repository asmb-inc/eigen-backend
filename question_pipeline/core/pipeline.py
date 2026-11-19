from . import generator, references, store
from .validator import answers_match, validate_question

# How many existing Eigen questions to show as style examples for a brand-new topic
STYLE_EXAMPLES = 3


def _check_and_save(generated: list[dict], verify: bool, reference_name: str) -> dict:
    """Validate -> (verify) -> save as drafts. Shared by every way of generating."""
    valid, invalid = [], []
    for q in generated:
        errors = validate_question(q)
        if errors:
            invalid.append({"question": q, "errors": errors})
            continue

        if verify:
            expected = [a["value"] for a in sorted(q["answers"], key=lambda a: a["blank_order"])]
            try:
                solved = generator.solve_question(q["body"], q["blanks_count"])
                q["verified"] = answers_match(expected, solved)
                q["verifier_answers"] = solved
            except (generator.LLMError, ValueError, TypeError):
                q["verified"] = False
                q["verifier_answers"] = None

        valid.append(q)

    saved = store.add_drafts(valid, reference=reference_name)
    return {"saved": saved, "invalid": invalid}


def _previous_bodies(reference_name: str) -> list[str]:
    """Latest problems generated from the same reference, so the LLM does not repeat them."""
    bodies = [q["body"] for q in store.list_questions() if q.get("reference") == reference_name and "body" in q]
    return bodies[-20:]


def run(reference: dict, count: int = 5, verify: bool = True, reference_name: str | None = None) -> dict:
    """Generate questions modelled on one existing Eigen question."""
    generated = generator.generate_questions(reference, count, avoid=_previous_bodies(reference_name))
    return _check_and_save(generated, verify, reference_name)


def run_for_topic(topic: str, count: int = 5, difficulty: int = 800, verify: bool = True) -> dict:
    """Generate `count` questions on a topic.

    If Eigen already has questions on it, they are used as references (spread across them).
    If not, a topic-only prompt is used, with a few Eigen questions shown just for style.
    `difficulty` is only used for a new topic; otherwise each reference's difficulty is kept.
    """
    refs = references.find_references(topic)

    if not refs:
        name = f"topic:{topic.strip().lower()}"
        examples = references.load_references()[:STYLE_EXAMPLES]
        generated = generator.generate_from_topic(topic, count, difficulty, examples, avoid=_previous_bodies(name))
        result = _check_and_save(generated, verify, name)
        return {**result, "used_references": [], "new_topic": True}

    # e.g. 5 questions over 2 references -> 3 from the first, 2 from the second
    per_ref = [count // len(refs) + (1 if i < count % len(refs) else 0) for i in range(len(refs))]
    saved, invalid = [], []
    for ref, n in zip(refs, per_ref):
        if n == 0:
            continue
        result = run(ref, n, verify, reference_name=ref["_file"])
        saved += result["saved"]
        invalid += result["invalid"]
    return {"saved": saved, "invalid": invalid, "used_references": [r["_file"] for r in refs], "new_topic": False}
