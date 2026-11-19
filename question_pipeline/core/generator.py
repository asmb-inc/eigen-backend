import json
import os
import re
import time
from urllib.parse import urlparse

import requests
from dotenv import load_dotenv

load_dotenv()

# Which LLM to use is set only in .env:
#   LLM_PROVIDER=ollama  -> Ollama's own API (local Ollama or Ollama cloud)
#   LLM_PROVIDER=openai  -> any OpenAI-compatible API: Groq, DeepSeek, Together, OpenAI ...
# The older OLLAMA_* names still work, so an existing .env keeps running.
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "ollama").strip().lower()
LLM_BASE_URL = (os.getenv("LLM_BASE_URL") or os.getenv("OLLAMA_HOST") or "http://localhost:11434").rstrip("/")
LLM_MODEL = os.getenv("LLM_MODEL") or os.getenv("OLLAMA_MODEL") or "qwen2.5:7b"
LLM_API_KEY = os.getenv("LLM_API_KEY") or os.getenv("OLLAMA_API_KEY")  # not needed for local Ollama
# OpenAI-compatible only. "Thinking" models like gpt-oss reason before answering; with a small output
# budget the answer gets cut off or comes back empty, so allow enough tokens and ask for less reasoning.
LLM_MAX_TOKENS = int(os.getenv("LLM_MAX_TOKENS") or 6000)
LLM_REASONING_EFFORT = os.getenv("LLM_REASONING_EFFORT", "").strip()  # low / medium / high; empty = not sent
RATE_LIMIT_RETRIES = 3


FORMAT_RULES = r"""You write physics and maths problems for Eigen, a competitive problem-solving app
(JEE / olympiad level). Problems are written in LaTeX and every answer is a number.

FORMAT RULES (a question that breaks these is thrown away):
- "body" is the problem statement. Write all maths in LaTeX using \( ... \) inline or $$ ... $$ for display.
  Units go in \mathrm{{...}}, e.g. \( 500\ \mathrm{{J}} \).
- Mark every value the solver must find with exactly this blank: \underline{{\hspace{{2cm}}}}
- "blanks_count" = number of blanks = number of items in "answers".
- Every answer is a single plain number: no units, no text, no fractions (write 0.5, not 1/2).
  Round non-exact answers to at most 3 decimal places.

"""

# Used when Eigen already has a problem on this topic
REFERENCE_TASK = r"""Here is a problem that already exists in Eigen. Create {count} NEW problems based on it.
- Keep the SAME concept, the SAME kind of quantity being asked for, and the SAME blank style
  as the reference (if the reference asks for F/blank, keep that form; if it asks for a value, ask for a value).
- Change the setting, the wording and the numbers, so it reads like a different problem.
  A short real-life situation is good. Do not copy the reference's sentences.
- A small twist is fine, but the solving method should stay the one the reference tests.
- Keep the difficulty close to the reference (difficulty {difficulty}, on a 500-2000 scale).
- Work out every answer yourself from your new numbers. Never reuse the reference's answer.
{avoid}
Reference problem:
{reference}

"""

# Used when the admin picks a topic Eigen has no problem on yet
TOPIC_TASK = r"""Create {count} NEW problems on the topic: {topic}.
- Eigen has no problem on this topic yet. The examples below only show Eigen's style
  (length, LaTeX, blank style, level). Do NOT copy their topic or their setting.
- Each problem must clearly test {topic} and need at least two steps of reasoning.
- Use a short real-life situation where it fits. Every problem must differ from the others.
- Aim for difficulty {difficulty} on a 500-2000 scale
  (500 = one or two direct steps, 2000 = long multi-step olympiad-style reasoning).
- Work out every answer yourself.
{avoid}
Style examples:
{examples}

"""

REPLY_SHAPE = r"""Reply with JSON only, in this shape:
{{
  "questions": [
    {{
      "title": "short catchy title",
      "body": "LaTeX problem text with \underline{{\hspace{{2cm}}}} for each blank",
      "blanks_count": 1,
      "answers": [{{"blank_order": 1, "value": 0}}],
      "topics": "{topics}",
      "difficulty": {difficulty},
      "angle": "one line: what you changed compared with the reference",
      "explanation": "step-by-step working that reaches each answer"
    }}
  ]
}}"""


SOLVE_PROMPT = """Solve this physics/maths problem. It has {blanks} answer(s), each a single number.
Blanks are marked \\underline{{\\hspace{{2cm}}}}; if none are marked, the answer is the quantity asked for.
Work it out carefully, then reply with JSON only:
{{"working": "your steps", "answers": [number for blank 1, number for blank 2, ...]}}
Write every answer as a plain decimal number (e.g. 0.2222), never as a fraction like 2/9 or an expression.

Problem:
{question}"""


class LLMError(Exception):
    pass


def _request_body(prompt: str, temperature: float) -> tuple[str, dict]:
    """URL and body for the configured provider."""
    messages = [{"role": "user", "content": prompt}]
    if LLM_PROVIDER == "openai":
        # No "response_format: json_object" here: with it, providers like Groq check the JSON on their
        # side and reject replies whose LaTeX backslashes are not escaped, before we can repair them.
        # The prompts already ask for JSON only, and _extract_json + _fix_latex_backslashes repair it.
        body = {
            "model": LLM_MODEL,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": LLM_MAX_TOKENS,
        }
        if LLM_REASONING_EFFORT:
            body["reasoning_effort"] = LLM_REASONING_EFFORT
        return f"{LLM_BASE_URL}/chat/completions", body
    return f"{LLM_BASE_URL}/api/chat", {
        "model": LLM_MODEL,
        "messages": messages,
        "format": "json",
        "stream": False,
        "options": {"temperature": temperature},
    }


def _chat(prompt: str, temperature: float = 0.2) -> dict:
    """Send one prompt to the LLM and return its reply parsed as JSON."""
    if LLM_PROVIDER not in ("ollama", "openai"):
        raise LLMError(f"LLM_PROVIDER must be 'ollama' or 'openai', got {LLM_PROVIDER!r}")

    url, body = _request_body(prompt, temperature)
    headers = {"Authorization": f"Bearer {LLM_API_KEY}"} if LLM_API_KEY else {}

    for attempt in range(RATE_LIMIT_RETRIES + 1):
        try:
            resp = requests.post(url, headers=headers, json=body, timeout=300)
        except requests.RequestException as e:
            raise LLMError(f"Could not reach the LLM at {LLM_BASE_URL}: {e}") from e

        # free plans limit tokens per minute; wait as long as the provider asks, then retry
        if resp.status_code == 429 and attempt < RATE_LIMIT_RETRIES:
            time.sleep(min(float(resp.headers.get("retry-after", 10)), 60))
            continue
        if not resp.ok:
            # show the provider's own reason, e.g. "Add usage credits" or "Invalid API key"
            host = urlparse(LLM_BASE_URL).netloc or LLM_BASE_URL
            raise LLMError(f"{host} refused the request ({resp.status_code}): {resp.text[:300]}")
        break

    data = resp.json()
    if LLM_PROVIDER == "openai":
        choice = data["choices"][0]
        if choice.get("finish_reason") == "length" and not (choice["message"].get("content") or "").rstrip().endswith("}"):
            raise LLMError(f"The answer was cut off at {LLM_MAX_TOKENS} tokens; raise LLM_MAX_TOKENS in .env")
        content = choice["message"]["content"]
    else:
        content = data["message"]["content"]
    try:
        # strict=False allows raw line breaks inside strings, which models often write
        text = _fix_latex_backslashes(_extract_json(content or ""))
        try:
            return json.loads(text, strict=False)
        except json.JSONDecodeError:
            return json.loads(_fractions_to_decimals(text), strict=False)
    except json.JSONDecodeError as e:
        raise LLMError(f"The LLM did not return valid JSON ({e}): {(content or '')[:200]}") from e


def _extract_json(text: str) -> str:
    """The JSON object inside a reply, even if the model wrapped it in ```json fences or added a sentence."""
    start, end = text.find("{"), text.rfind("}")
    return text[start:end + 1] if start != -1 and end > start else text


# a fraction standing alone as a list item, e.g. the 2/9 in "answers": [2/9, 0.5]
_LIST_FRACTION = re.compile(r"(?<=[\[,])(\s*)(-?\d+(?:\.\d+)?)\s*/\s*(\d+(?:\.\d+)?)(?=\s*[\],])")


def _fractions_to_decimals(text: str) -> str:
    """Models sometimes answer [2/9], which is maths but not JSON; turn such list items into decimals."""
    def to_decimal(m: re.Match) -> str:
        denominator = float(m.group(3))
        return m.group(0) if denominator == 0 else f"{m.group(1)}{float(m.group(2)) / denominator:.6g}"

    return _LIST_FRACTION.sub(to_decimal, text)


# LaTeX commands that start with \n, which JSON would otherwise read as a newline
_LATEX_N = re.compile(r"n(?:u|abla|eq|e|eg|ot|ewline|mid|i)(?![a-zA-Z])")


def _fix_latex_backslashes(text: str) -> str:
    r"""LaTeX inside JSON strings needs doubled backslashes; models sometimes forget.

    A lone backslash is doubled when it starts a LaTeX command. Without this, \underline
    breaks the JSON, and worse, \frac and \times parse "fine" as form-feed + "rac" and tab + "imes".
    Real JSON escapes (\" \\ \/ \uXXXX, and \n \t etc. not followed by a letter) are kept.
    """
    def fix(m: re.Match) -> str:
        rest = text[m.end():]
        nxt = rest[:1]
        if nxt in ('"', "\\", "/") or re.match(r"u[0-9a-fA-F]{4}", rest):
            return m.group()
        if nxt in "bfrt" and nxt and not rest[1:2].isalpha():
            return m.group()  # genuine \t, \r ... escape
        if nxt == "n" and not _LATEX_N.match(rest):
            return m.group()  # genuine newline
        return "\\\\"

    # (?<!\\) skips the second backslash of an already-doubled pair
    return re.sub(r"(?<!\\)\\", fix, text)


def _avoid_block(avoid: list[str] | None) -> str:
    if not avoid:
        return ""
    listed = "\n".join(f"- {text}" for text in avoid)
    return f"\nThese problems already exist. Do not repeat their setting, structure or reasoning:\n{listed}\n"


def _shown(question: dict) -> dict:
    return {k: question.get(k) for k in ("title", "body", "blanks_count", "answers", "topics", "difficulty")}


def _ask_for_questions(prompt: str, topics: str, difficulty: int) -> list[dict]:
    # Higher temperature = more varied ideas. Solving stays at the low default so it is precise.
    # Long LaTeX replies occasionally come back broken, so try once more before giving up.
    try:
        data = _chat(prompt, temperature=0.9)
    except LLMError:
        data = _chat(prompt, temperature=0.9)
    questions = data.get("questions")
    if not isinstance(questions, list):
        raise LLMError("LLM reply has no 'questions' list")
    for q in questions:
        if not isinstance(q, dict):
            continue
        for field in ("title", "body", "explanation", "angle"):
            if isinstance(q.get(field), str):
                q[field] = _undo_double_escaping(q[field])

        # Models sometimes leave out fields we already know. Topics and difficulty come from the
        # reference (or the admin's choice), so fill them in; the admin can still change them in review.
        if not (isinstance(q.get("topics"), str) and q["topics"].strip()):
            q["topics"] = topics
        d = q.get("difficulty")
        if isinstance(d, bool) or not isinstance(d, int) or d <= 0:
            q["difficulty"] = difficulty
        if q.get("blanks_count") is None and isinstance(q.get("answers"), list):
            q["blanks_count"] = len(q["answers"])  # the validator still checks it against the blanks in the body
    return questions


def generate_questions(reference: dict, count: int = 5, avoid: list[str] | None = None) -> list[dict]:
    """Ask the LLM for new questions modelled on one existing Eigen question.

    `avoid` is a list of problem bodies already generated, so the LLM does not repeat them.
    """
    values = {
        "count": count,
        "difficulty": reference.get("difficulty", 500),
        "topics": reference.get("topics", ""),
        "avoid": _avoid_block(avoid),
        "reference": json.dumps(_shown(reference), indent=2, ensure_ascii=False),
    }
    prompt = (FORMAT_RULES + REFERENCE_TASK + REPLY_SHAPE).format(**values)
    return _ask_for_questions(prompt, values["topics"], values["difficulty"])


def generate_from_topic(
    topic: str, count: int, difficulty: int, examples: list[dict], avoid: list[str] | None = None
) -> list[dict]:
    """Ask the LLM for questions on a topic Eigen has no question on yet. `examples` only show the style."""
    values = {
        "count": count,
        "topic": topic,
        "difficulty": difficulty,
        "topics": topic,
        "avoid": _avoid_block(avoid),
        "examples": "\n\n".join(json.dumps(_shown(e), indent=2, ensure_ascii=False) for e in examples),
    }
    prompt = (FORMAT_RULES + TOPIC_TASK + REPLY_SHAPE).format(**values)
    return _ask_for_questions(prompt, topic, difficulty)


def _undo_double_escaping(text: str) -> str:
    r"""Some replies escape twice, leaving "\\(" and a literal "\n" in the text. Turn them back into "\(" and a newline."""
    text = re.sub(r"\\\\(?=[a-zA-Z()\[\]{}])", r"\\", text)
    # a literal backslash-n that is not a LaTeX command like \nu or \neq was meant as a line break
    return re.sub(r"\\n(?![a-zA-Z])|\\n(?=[A-Z])", "\n", text)


def solve_question(body: str, blanks_count: int) -> list[float]:
    """Ask the LLM to solve a question without seeing the answer. Used to double-check answers."""
    prompt = SOLVE_PROMPT.format(blanks=blanks_count, question=body)
    for attempt in range(2):
        try:
            answers = _chat(prompt).get("answers")
            if isinstance(answers, list):
                return [float(a) for a in answers]
        except (LLMError, ValueError, TypeError):
            if attempt == 1:
                raise
    raise LLMError("LLM solve reply has no 'answers' list")
