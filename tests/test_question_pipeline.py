"""Tests for the AI question pipeline and the admin routes.

They use a fake LLM and a fake Supabase, so they need no API keys, no internet
and never touch real data. Run from the repo root:

    python -m unittest discover tests
"""
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

import dependencies
from question_pipeline.core import eigen_db, generator, pipeline, references, store
from question_pipeline.core.validator import BLANK, answers_match, validate_question
from routes import admin_questions_routes


def make_question(value=5, **changes):
    q = {
        "title": "Lens",
        "body": f"Find the image distance: {BLANK} cm",
        "blanks_count": 1,
        "answers": [{"blank_order": 1, "value": value}],
        "topics": "optics, physics",
        "difficulty": 500,
        "explanation": "1/v = 1/f - 1/u",
    }
    q.update(changes)
    return q


class TempStoreTestCase(unittest.TestCase):
    """Points the store at a temporary folder so tests never touch question_pipeline/data."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        tmp = Path(self.tmp.name)
        for name, value in {
            "DATA_DIR": tmp,
            "QUESTIONS_FILE": tmp / "questions.json",
            "PUBLISHED_FILE": tmp / "published.json",
        }.items():
            p = patch.object(store, name, value)
            p.start()
            self.addCleanup(p.stop)

    def tearDown(self):
        self.tmp.cleanup()


class ValidatorTests(unittest.TestCase):
    def test_valid_question_passes(self):
        self.assertEqual(validate_question(make_question()), [])

    def test_blank_and_answer_count_must_match(self):
        q = make_question(answers=[{"blank_order": 1, "value": 1}, {"blank_order": 2, "value": 2}])
        self.assertTrue(any("blanks_count" in e for e in validate_question(q)))

    def test_answer_must_be_a_number(self):
        errors = validate_question(make_question(value="80 km/h"))
        self.assertTrue(any("must be a number" in e for e in errors))

    def test_difficulty_must_be_positive_whole_number(self):
        for bad in (0, -5, "hard", True):
            self.assertTrue(validate_question(make_question(difficulty=bad)), bad)

    def test_single_unmarked_blank_is_allowed(self):
        # some existing Eigen questions just say "Find ..." with no blank marker
        self.assertEqual(validate_question(make_question(body="Find the image distance v.")), [])

    def test_answers_match_uses_eigen_tolerance(self):
        self.assertTrue(answers_match([24], [24.0001]))
        self.assertFalse(answers_match([0.34], [0.3412]))


class LatexCleanupTests(unittest.TestCase):
    def test_single_backslash_latex_survives_json(self):
        raw = r'{"b": "\frac{1}{2} \times \theta \nu \underline{\hspace{2cm}}"}'
        body = json.loads(generator._fix_latex_backslashes(raw))["b"]
        self.assertEqual(body, r"\frac{1}{2} \times \theta \nu \underline{\hspace{2cm}}")

    def test_real_json_escapes_are_kept(self):
        raw = r'{"b": "line one\nline two\t\"quoted\""}'
        self.assertEqual(json.loads(generator._fix_latex_backslashes(raw))["b"], 'line one\nline two\t"quoted"')

    def test_double_escaped_text_is_undone(self):
        self.assertEqual(generator._undo_double_escaping(r"\\( x \\) step\nNext"), "\\( x \\) step\nNext")


class MissingFieldsTests(unittest.TestCase):
    def test_known_fields_are_filled_from_the_reference(self):
        # the model "forgot" topics, difficulty and blanks_count
        reply = {"questions": [{k: v for k, v in make_question().items() if k not in ("topics", "difficulty", "blanks_count")}]}
        with patch.object(generator, "_chat", return_value=reply):
            q = generator.generate_questions(make_question(topics="optics, physics", difficulty=500), 1)[0]
        self.assertEqual((q["topics"], q["difficulty"], q["blanks_count"]), ("optics, physics", 500, 1))
        self.assertEqual(validate_question(q), [])

    def test_missing_explanation_is_still_rejected(self):
        reply = {"questions": [{k: v for k, v in make_question().items() if k != "explanation"}]}
        with patch.object(generator, "_chat", return_value=reply):
            q = generator.generate_questions(make_question(), 1)[0]
        self.assertIn("explanation is missing or empty", validate_question(q))


class PipelineTests(TempStoreTestCase):
    def test_valid_questions_saved_as_drafts_and_invalid_dropped(self):
        generated = [make_question(5), make_question(7), make_question(value="oops")]
        with patch.object(generator, "generate_questions", return_value=generated), \
             patch.object(generator, "solve_question", return_value=[5.0]):
            result = pipeline.run(make_question(), count=3, reference_name="q9.json")

        self.assertEqual(len(result["saved"]), 2)
        self.assertEqual(len(result["invalid"]), 1)
        drafts = store.list_questions("draft")
        self.assertEqual([q["verified"] for q in drafts], [True, False])  # verifier caught the wrong 7
        self.assertTrue(all(q["source"] == "ai" for q in drafts))

    def test_known_topic_uses_its_references(self):
        refs = [{**make_question(), "_file": "q9.json"}]
        with patch.object(references, "load_references", return_value=refs), \
             patch.object(generator, "generate_questions", return_value=[make_question()]) as gen, \
             patch.object(generator, "solve_question", return_value=[5.0]):
            result = pipeline.run_for_topic("optics", count=1)

        self.assertFalse(result["new_topic"])
        self.assertEqual(result["used_references"], ["q9.json"])
        gen.assert_called_once()

    def test_new_topic_is_generated_without_a_reference(self):
        with patch.object(references, "load_references", return_value=[]), \
             patch.object(generator, "generate_from_topic", return_value=[make_question()]) as gen, \
             patch.object(generator, "solve_question", return_value=[5.0]):
            result = pipeline.run_for_topic("probability", count=1, difficulty=900)

        self.assertTrue(result["new_topic"])
        self.assertEqual(gen.call_args.args[2], 900)


class StoreTests(TempStoreTestCase):
    def test_approve_then_publish(self):
        q = store.add_drafts([make_question()])[0]
        store.set_status(q["id"], "approved")
        result = store.publish_approved()
        self.assertEqual([p["id"] for p in result["published"]], [q["id"]])
        self.assertEqual(store.get_question(q["id"])["status"], "published")
        self.assertTrue(store.PUBLISHED_FILE.exists())

    def test_failed_push_keeps_question_approved(self):
        q = store.add_drafts([make_question()])[0]
        store.set_status(q["id"], "approved")

        def push(question):
            raise RuntimeError("database down")

        result = store.publish_approved(push)
        self.assertEqual(result["published"], [])
        self.assertEqual(store.get_question(q["id"])["status"], "approved")


class AdminRouteTests(TempStoreTestCase):
    def setUp(self):
        super().setUp()
        app = FastAPI()
        app.include_router(admin_questions_routes.router)
        self.user = {"id": "u1", "email": "admin@eigen.test"}
        app.dependency_overrides[dependencies.get_current_user] = lambda: self.user
        self.client = TestClient(app)

        for p in (
            patch.dict(os.environ, {"ADMIN_EMAILS": "admin@eigen.test"}),
            patch.object(eigen_db, "has_service_key", return_value=False),
            patch.object(references, "load_references", return_value=[{**make_question(), "_file": "q9.json"}]),
            patch.object(generator, "generate_questions", return_value=[make_question(), make_question()]),
            patch.object(generator, "solve_question", return_value=[5.0]),
        ):
            p.start()
            self.addCleanup(p.stop)

    def test_non_admin_is_blocked(self):
        self.user = {"id": "u2", "email": "student@eigen.test"}
        self.assertEqual(self.client.get("/admin/questions").status_code, 403)

    def test_generate_needs_a_topic(self):
        self.assertEqual(self.client.post("/admin/questions/generate", json={}).status_code, 400)

    def test_full_review_flow(self):
        job = self.client.post("/admin/questions/generate", json={"topic": "optics", "count": 2})
        self.assertEqual(job.status_code, 202)
        self.assertEqual(self.client.get(f"/admin/questions/jobs/{job.json()['id']}").json()["status"], "done")

        drafts = self.client.get("/admin/questions", params={"status": "draft"}).json()
        self.assertEqual(len(drafts), 2)
        a, b = drafts[0]["id"], drafts[1]["id"]

        bad_edit = {"answers": [{"blank_order": 1, "value": 1}, {"blank_order": 2, "value": 2}]}
        self.assertEqual(self.client.patch(f"/admin/questions/{a}", json=bad_edit).status_code, 400)
        self.assertEqual(self.client.patch(f"/admin/questions/{a}", json={"difficulty": 650}).json()["difficulty"], 650)

        self.assertEqual(self.client.post(f"/admin/questions/{a}/approve").json()["status"], "approved")
        self.assertEqual(self.client.post(f"/admin/questions/{b}/reject", json={"note": "too easy"}).json()["status"], "rejected")

        published = self.client.post("/admin/questions/publish").json()
        self.assertEqual(published["published_count"], 1)
        self.assertFalse(published["saved_to_eigen"])  # no service key in this test
        self.assertEqual(self.client.patch(f"/admin/questions/{a}", json={"difficulty": 700}).status_code, 400)

    def test_publish_sends_question_and_answers_to_eigen(self):
        q = store.add_drafts([make_question()])[0]
        store.set_status(q["id"], "approved")
        calls = []

        def fake_supabase(method, path, key, **kwargs):
            calls.append((method, path))
            return [{"id": 101}] if path == "/rest/v1/questions" else None

        with patch.object(eigen_db, "has_service_key", return_value=True), \
             patch.object(eigen_db, "is_admin", return_value=True), \
             patch.object(eigen_db, "_request", side_effect=fake_supabase):
            result = self.client.post("/admin/questions/publish").json()

        self.assertEqual(result["published"][0]["eigen_question_id"], 101)
        self.assertEqual(calls, [("POST", "/rest/v1/questions"), ("POST", "/rest/v1/answers")])


class FakeResponse:
    def __init__(self, status, payload=None, text="", headers=None):
        self.status_code, self._payload, self.text, self.headers = status, payload, text, headers or {}
        self.ok = status < 400

    def json(self):
        return self._payload


class ProviderTests(unittest.TestCase):
    """The same prompt goes to Ollama or an OpenAI-compatible API (Groq...) depending on .env."""

    def use(self, provider, base):
        settings = {"LLM_PROVIDER": provider, "LLM_BASE_URL": base, "LLM_MODEL": "m", "LLM_API_KEY": "k",
                    "LLM_MAX_TOKENS": 6000, "LLM_REASONING_EFFORT": "low"}
        for name, value in settings.items():
            p = patch.object(generator, name, value)
            p.start()
            self.addCleanup(p.stop)

    def test_openai_compatible_format(self):
        self.use("openai", "https://api.groq.com/openai/v1")
        reply = FakeResponse(200, {"choices": [{"message": {"content": '{"answers": [3]}'}}]})
        with patch.object(generator.requests, "post", return_value=reply) as post:
            self.assertEqual(generator._chat("hi"), {"answers": [3]})
        self.assertEqual(post.call_args.args[0], "https://api.groq.com/openai/v1/chat/completions")
        # no strict JSON mode: with it Groq rejects replies whose LaTeX we could have repaired
        sent = post.call_args.kwargs["json"]
        self.assertNotIn("response_format", sent)
        # enough room for "thinking" models to finish their answer
        self.assertEqual((sent["max_tokens"], sent["reasoning_effort"]), (6000, "low"))
        self.assertEqual(post.call_args.kwargs["headers"], {"Authorization": "Bearer k"})

    def test_cut_off_answer_gives_a_clear_error(self):
        self.use("openai", "https://api.groq.com/openai/v1")
        reply = FakeResponse(200, {"choices": [{"finish_reason": "length", "message": {"content": ""}}]})
        with patch.object(generator.requests, "post", return_value=reply):
            with self.assertRaises(generator.LLMError) as ctx:
                generator._chat("hi")
        self.assertIn("raise LLM_MAX_TOKENS", str(ctx.exception))

    def test_json_wrapped_in_fences_with_unescaped_latex(self):
        self.use("openai", "https://api.groq.com/openai/v1")
        # what the model really sends: a sentence, ```json fences, and single (unescaped) LaTeX backslashes
        content = 'Here you go:\n```json\n{"body": "Find ' + "\\(v\\): \\underline{\\hspace{2cm}}" + '"}\n```'
        reply = FakeResponse(200, {"choices": [{"message": {"content": content}}]})
        with patch.object(generator.requests, "post", return_value=reply):
            self.assertEqual(generator._chat("hi"), {"body": r"Find \(v\): \underline{\hspace{2cm}}"})

    def test_fraction_answers_become_decimals(self):
        self.use("openai", "https://api.groq.com/openai/v1")
        content = '{"working": "(1/2)*(4/9) = 2/9.", "answers": [2/9, 0.5, 3 / 4]}'
        reply = FakeResponse(200, {"choices": [{"message": {"content": content}}]})
        with patch.object(generator.requests, "post", return_value=reply):
            result = generator._chat("hi")
        self.assertEqual(result["working"], "(1/2)*(4/9) = 2/9.")  # text inside strings is left alone
        self.assertEqual(result["answers"], [0.222222, 0.5, 0.75])

    def test_ollama_format(self):
        self.use("ollama", "https://ollama.com")
        reply = FakeResponse(200, {"message": {"content": '{"answers": [3]}'}})
        with patch.object(generator.requests, "post", return_value=reply) as post:
            self.assertEqual(generator._chat("hi"), {"answers": [3]})
        self.assertEqual(post.call_args.args[0], "https://ollama.com/api/chat")
        self.assertEqual(post.call_args.kwargs["json"]["format"], "json")

    def test_provider_refusal_shows_the_real_reason(self):
        self.use("ollama", "https://ollama.com")
        reply = FakeResponse(402, text='{"error":"Add usage credits or subscribe"}')
        with patch.object(generator.requests, "post", return_value=reply):
            with self.assertRaises(generator.LLMError) as ctx:
                generator._chat("hi")
        self.assertIn("ollama.com refused the request (402)", str(ctx.exception))
        self.assertIn("Add usage credits", str(ctx.exception))

    def test_rate_limit_waits_and_retries(self):
        self.use("openai", "https://api.groq.com/openai/v1")
        limited = FakeResponse(429, text="rate limit", headers={"retry-after": "2"})
        ok = FakeResponse(200, {"choices": [{"message": {"content": '{"answers": [1]}'}}]})
        with patch.object(generator.requests, "post", side_effect=[limited, limited, ok]) as post, \
             patch.object(generator.time, "sleep") as sleep:
            self.assertEqual(generator._chat("hi"), {"answers": [1]})
        self.assertEqual(post.call_count, 3)
        self.assertEqual(sleep.call_count, 2)

    def test_rate_limit_gives_up_after_three_waits(self):
        self.use("openai", "https://api.groq.com/openai/v1")
        limited = FakeResponse(429, text="Rate limit reached", headers={"retry-after": "1"})
        with patch.object(generator.requests, "post", return_value=limited), \
             patch.object(generator.time, "sleep"):
            with self.assertRaises(generator.LLMError) as ctx:
                generator._chat("hi")
        self.assertIn("(429)", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
