import math

# Eigen marks a blank in the LaTeX body like this
BLANK = r"\underline{\hspace{2cm}}"


def validate_question(q: dict) -> list[str]:
    """Return a list of problems. Empty list means the question matches Eigen's format."""
    errors = []

    for field in ("title", "body", "topics", "explanation"):
        if not isinstance(q.get(field), str) or not q[field].strip():
            errors.append(f"{field} is missing or empty")

    answers = q.get("answers")
    if not isinstance(answers, list) or not answers:
        errors.append("answers must be a non-empty list")
        answers = []

    blanks_count = q.get("blanks_count")
    if blanks_count != len(answers):
        errors.append(f"blanks_count is {blanks_count!r} but there are {len(answers)} answers")

    # Existing Eigen questions either mark every blank, or have one unmarked "Find ..." blank
    markers = (q.get("body") or "").count(BLANK)
    if markers != len(answers) and not (markers == 0 and len(answers) == 1):
        errors.append(f"body has {markers} blank markers but there are {len(answers)} answers")

    # Eigen checks answers by blank_order, so it must be 1, 2, 3 ... with no gaps
    orders = [a.get("blank_order") for a in answers if isinstance(a, dict)]
    if sorted(orders) != list(range(1, len(answers) + 1)):
        errors.append(f"blank_order must be 1..{len(answers)}, got {orders}")

    for a in answers:
        value = a.get("value") if isinstance(a, dict) else None
        # bool is a subclass of int in Python, so reject it explicitly
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            errors.append(f"answer value must be a number, got {value!r}")

    # Difficulty is set by a person, same as before; it is also the contest score, so it must be a positive number
    difficulty = q.get("difficulty")
    if isinstance(difficulty, bool) or not isinstance(difficulty, int) or difficulty <= 0:
        errors.append(f"difficulty must be a positive whole number, got {difficulty!r}")

    return errors


def answers_match(expected: list[float], got: list[float]) -> bool:
    """Same tolerance Eigen uses when checking user answers."""
    if len(expected) != len(got):
        return False
    return all(math.isclose(e, g, rel_tol=1e-3, abs_tol=1e-3) for e, g in zip(expected, got))
