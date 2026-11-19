"""Terminal interface for the question pipeline.

Run from the repo root:
    python -m question_pipeline.cli fetch-references
    python -m question_pipeline.cli generate --reference question_pipeline/data/references/q14.json --count 5
    python -m question_pipeline.cli list --status draft
    python -m question_pipeline.cli review
    python -m question_pipeline.cli publish
"""
import argparse
import json
import sys

from pathlib import Path

from .core import eigen_db, pipeline, references, store
from .core.generator import LLMError
from .core.validator import validate_question


def show(q: dict) -> None:
    print("-" * 60)
    print(f"id: {q['id']}   status: {q['status']}   difficulty: {q.get('difficulty')}   topics: {q.get('topics')}")
    if q.get("angle"):
        print(f"angle: {q['angle']}")
    print(f"\ntitle: {q.get('title')}")
    print(f"\n{q.get('body')}\n")
    for a in sorted(q.get("answers", []), key=lambda a: a["blank_order"]):
        print(f"  blank {a['blank_order']}: {a['value']}")
    print(f"\nexplanation: {q.get('explanation')}")
    if "verified" in q:
        mark = "OK - matches" if q["verified"] else "MISMATCH - check carefully!"
        print(f"verifier: {mark} (verifier got {q.get('verifier_answers')})")


def cmd_topics(args) -> None:
    topics = references.list_topics()
    if not topics:
        sys.exit("No references found. Run: python -m question_pipeline.cli fetch-references")
    for name, n in topics.items():
        print(f"{name:<18} {n} reference question(s)")
    print("\nAny other topic also works; it will be generated without a reference.")


def cmd_generate(args) -> None:
    if args.topic:
        print(f"Generating {args.count} questions on '{args.topic}'... (this can take a few minutes)")
        try:
            result = pipeline.run_for_topic(args.topic, args.count, args.difficulty, verify=not args.no_verify)
        except LLMError as e:
            sys.exit(f"Error: {e}")
        if result["new_topic"]:
            print(f"No Eigen question on this topic yet - generated from the topic alone (difficulty {args.difficulty}).")
        else:
            print(f"Based on: {', '.join(result['used_references'])}")
        print(f"Saved {len(result['saved'])} drafts.")
        for item in result["invalid"]:
            print(f"Dropped 1 invalid question: {'; '.join(item['errors'])}")
        print("\nNext: python -m question_pipeline.cli review")
        return

    if args.all:
        paths = sorted((store.DATA_DIR / "references").glob("q*.json"))
        if not paths:
            sys.exit("No references found. Run: python -m question_pipeline.cli fetch-references")
    elif args.reference:
        paths = [Path(args.reference)]
    else:
        sys.exit("Give --topic <name>, --reference <file> or --all")

    for path in paths:
        reference = json.loads(path.read_text(encoding="utf-8"))
        print(f"\n[{path.name}] {reference.get('title')}: generating {args.count}... (this can take a minute)")
        try:
            result = pipeline.run(reference, count=args.count, verify=not args.no_verify, reference_name=path.name)
        except LLMError as e:
            print(f"Error: {e}")
            continue
        print(f"Saved {len(result['saved'])} drafts.")
        for item in result["invalid"]:
            print(f"Dropped 1 invalid question: {'; '.join(item['errors'])}")

    print("\nNext: python -m question_pipeline.cli review")


def cmd_fetch_references(args) -> None:
    """Save every existing Eigen question as a reference file (read-only on the database)."""
    out = store.DATA_DIR / "references"
    out.mkdir(parents=True, exist_ok=True)
    for q in eigen_db.fetch_questions():
        if len(q["answers"]) != q["blanks_count"]:
            print(f"Skipped q{q['id']} ({q['title']}): {len(q['answers'])} answers but blanks_count {q['blanks_count']}")
            continue
        path = out / f"q{q['id']}.json"
        path.write_text(json.dumps(q, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"{path.name:<9} difficulty {q['difficulty']:>5}  {q['topics']:<22}  {q['title']}")
    print("\nNext: python -m question_pipeline.cli generate --reference question_pipeline/data/references/q14.json --count 3")


def cmd_list(args) -> None:
    questions = store.list_questions(args.status)
    if not questions:
        print("No questions found.")
    for q in questions:
        print(f"{q['id']}  [{q['status']}]  {q.get('title') or q.get('body', '')[:70]}")


def edit_question(q: dict) -> dict:
    """Open the question as JSON, let the user paste a corrected version."""
    editable = {k: q[k] for k in ("title", "body", "blanks_count", "answers", "topics", "difficulty", "angle", "explanation") if k in q}
    print("\nCurrent JSON:\n" + json.dumps(editable, indent=2, ensure_ascii=False))
    print("\nPaste the corrected JSON, then type END on its own line:")
    lines = []
    for line in sys.stdin:
        if line.strip() == "END":
            break
        lines.append(line)
    try:
        changes = json.loads("".join(lines))
    except json.JSONDecodeError as e:
        print(f"Invalid JSON, edit cancelled: {e}")
        return q

    errors = validate_question({**q, **changes})
    if errors:
        print("Edit not saved, problems found:\n  " + "\n  ".join(errors))
        return q
    return store.update_question(q["id"], changes)


def cmd_review(args) -> None:
    drafts = store.list_questions("draft")
    if not drafts:
        print("No drafts to review.")
        return

    print(f"{len(drafts)} drafts to review.")
    for i, q in enumerate(drafts, 1):
        print(f"\n[{i}/{len(drafts)}]")
        while True:
            show(q)
            choice = input("\n(a)pprove  (r)eject  (e)dit  (s)kip  (q)uit > ").strip().lower()
            if choice == "a":
                store.set_status(q["id"], "approved")
                print("Approved.")
                break
            if choice == "r":
                note = input("Reason (optional): ").strip() or None
                store.set_status(q["id"], "rejected", note)
                print("Rejected.")
                break
            if choice == "e":
                q = edit_question(q)
                continue  # show the edited version and ask again
            if choice == "s":
                break
            if choice == "q":
                return
            print("Please type a, r, e, s or q.")

    print("\nReview done. Next: python -m question_pipeline.cli publish")


REPORT_TEMPLATE = """<!doctype html>
<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Eigen AI Questions</title>
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/katex@0.16.9/dist/katex.min.css">
<script defer src="https://cdn.jsdelivr.net/npm/katex@0.16.9/dist/katex.min.js"></script>
<script defer src="https://cdn.jsdelivr.net/npm/katex@0.16.9/dist/contrib/auto-render.min.js"
  onload="renderMathInElement(document.body, {{delimiters: [
    {{left: '$$', right: '$$', display: true}}, {{left: '\\\\(', right: '\\\\)', display: false}},
    {{left: '$', right: '$', display: false}}], throwOnError: false}})"></script>
<style>
  body {{ font-family: system-ui, sans-serif; max-width: 860px; margin: 0 auto; padding: 16px; color: #1d1d1f; background: #fafafa; line-height: 1.5; }}
  .card {{ background: #fff; border: 1px solid #ddd; border-radius: 10px; padding: 16px; margin: 14px 0; }}
  .meta {{ font-size: 13px; color: #666; }}
  .tag {{ display: inline-block; padding: 1px 8px; border-radius: 10px; font-size: 12px; margin-right: 6px; }}
  .ok {{ background: #e3f6e8; color: #1b6e33; }} .bad {{ background: #fde8e8; color: #a12020; }}
  .ans {{ font-weight: 600; }} details {{ margin-top: 8px; font-size: 14px; color: #333; }}
  .body {{ white-space: pre-wrap; }}
</style></head><body>
<h1>Eigen AI-generated questions</h1>
<p class="meta">{summary}</p>
{cards}
</body></html>"""


def cmd_export(args) -> None:
    """Write an HTML page with the questions (maths rendered) to share for review."""
    from html import escape

    questions = store.list_questions(args.status)
    cards = []
    for i, q in enumerate(questions, 1):
        answers = ", ".join(str(a["value"]) for a in sorted(q.get("answers", []), key=lambda a: a["blank_order"]))
        verified = q.get("verified")
        tag = '<span class="tag ok">verifier OK</span>' if verified else '<span class="tag bad">verifier mismatch</span>'
        cards.append(
            f'<div class="card"><div class="meta">#{i} · {escape(q["status"])} · difficulty {q.get("difficulty")} · '
            f'{escape(str(q.get("topics")))} · based on {escape(str(q.get("reference")))}</div>'
            f'<h3>{escape(str(q.get("title")))}</h3><div class="body">{escape(str(q.get("body")))}</div>'
            f'<p>{tag}<span class="ans">Answer: {escape(answers)}</span></p>'
            f'<details><summary>Explanation</summary><div class="body">{escape(str(q.get("explanation")))}</div></details></div>'
        )
    ok = sum(1 for q in questions if q.get("verified"))
    summary = f"{len(questions)} questions · {ok} passed the verifier" + (f" · status: {args.status}" if args.status else "")
    out = store.DATA_DIR / "report.html"
    out.write_text(REPORT_TEMPLATE.format(summary=summary, cards="\n".join(cards)), encoding="utf-8")
    print(f"Wrote {len(questions)} questions -> {out}")


def cmd_publish(args) -> None:
    push = eigen_db.insert_question if eigen_db.has_service_key() else None
    result = store.publish_approved(push)
    where = "Eigen database + " if push else ""
    print(f"Published {len(result['published'])} questions -> {where}{store.PUBLISHED_FILE}")
    if not push:
        print("(SUPABASE_SERVICE_KEY not set: published to the local file only)")
    for f in result["failed"]:
        print(f"Could not publish {f['id']}, it stays approved: {f['error']}")


def cmd_create_admin(args) -> None:
    """Create an admin login. Needs SUPABASE_SERVICE_KEY; the password is typed hidden, never in the command."""
    from getpass import getpass

    if not eigen_db.has_service_key():
        sys.exit("Set SUPABASE_SERVICE_KEY in .env first.")
    password = getpass("Password for the new admin (hidden): ")
    if len(password) < 8 or password != getpass("Type it again: "):
        sys.exit("Passwords did not match or are shorter than 8 characters.")
    try:
        user_id = eigen_db.create_admin(args.email, password)
    except RuntimeError as e:
        sys.exit(f"Error: {e}")
    print(f"Admin created: {args.email} ({user_id})")


def main() -> None:
    # Windows terminals default to a non-UTF-8 encoding, which garbles maths symbols like × and ÷
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Eigen question generation pipeline")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("fetch-references", help="download existing Eigen questions to use as references").set_defaults(func=cmd_fetch_references)
    sub.add_parser("topics", help="list topics that have reference questions").set_defaults(func=cmd_topics)

    p = sub.add_parser("generate", help="generate draft questions with the LLM set in .env")
    p.add_argument("--reference", help="path to a reference question JSON file")
    p.add_argument("--all", action="store_true", help="use every file in data/references as a reference")
    p.add_argument("--topic", help="generate on a topic, e.g. optics or physics (see the topics command)")
    p.add_argument("--difficulty", type=int, default=800, help="difficulty for a topic with no existing question (500-2000)")
    p.add_argument("--count", type=int, default=5)
    p.add_argument("--no-verify", action="store_true", help="skip the second LLM call that re-solves each question")
    p.set_defaults(func=cmd_generate)

    p = sub.add_parser("list", help="list questions")
    p.add_argument("--status", choices=store.STATUSES)
    p.set_defaults(func=cmd_list)

    sub.add_parser("review", help="approve / reject / edit drafts").set_defaults(func=cmd_review)
    sub.add_parser("publish", help="publish all approved questions").set_defaults(func=cmd_publish)

    p = sub.add_parser("create-admin", help="create an admin login (needs SUPABASE_SERVICE_KEY)")
    p.add_argument("--email", required=True)
    p.set_defaults(func=cmd_create_admin)

    p = sub.add_parser("export", help="write an HTML report of the questions to share")
    p.add_argument("--status", choices=store.STATUSES)
    p.set_defaults(func=cmd_export)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
