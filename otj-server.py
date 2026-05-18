import csv
import json
import logging
import os
import threading
from datetime import date
from difflib import unified_diff

import anthropic
from dotenv import load_dotenv
from flask import Flask, jsonify, request

from puncher import prepare_browser, login_and_submit_otjs

load_dotenv()

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
for _noisy in ("selenium", "urllib3", "werkzeug"):
    logging.getLogger(_noisy).setLevel(logging.WARNING)
log = logging.getLogger(__name__)

app = Flask(__name__)

_browser_driver = None
_browser_lock = threading.Lock()


def _init_browser():
    global _browser_driver
    log.info("Pre-loading browser to OTP page...")
    try:
        driver = prepare_browser()
        with _browser_lock:
            _browser_driver = driver
        log.info("Browser ready at OTP page")
    except Exception as e:
        log.error("Failed to pre-load browser: %s", e)


threading.Thread(target=_init_browser, daemon=True).start()

NOTES_FILE  = os.path.join(os.path.dirname(__file__), 'notes.txt')
OTJ_CSV     = os.path.join(os.path.dirname(__file__), 'otjs.csv')
PROMPT_FILE = os.path.join(os.path.dirname(__file__), 'llm_prompt.txt')

anthropic_client = anthropic.Anthropic(api_key=os.getenv('ANTHROPIC_API_KEY'))


def compute_diff(new_content: str) -> str | None:
    if not os.path.exists(NOTES_FILE):
        log.info("notes.txt does not exist — creating it and treating all content as new")
        with open(NOTES_FILE, 'w') as f:
            f.write(new_content)
        log.debug("notes.txt created with %d characters", len(new_content))
        return new_content

    with open(NOTES_FILE, 'r') as f:
        old_content = f.read()

    log.debug("notes.txt read: %d characters", len(old_content))

    old_lines = old_content.splitlines(keepends=True)
    new_lines = new_content.splitlines(keepends=True)

    added = [
        line[1:]
        for line in unified_diff(old_lines, new_lines, n=0)
        if line.startswith('+') and not line.startswith('+++')
    ]

    if not added:
        log.info("Diff produced no new lines — incoming content is identical to notes.txt")
        return None

    diff = ''.join(added)
    log.info("Diff found %d new line(s):\n%s", len(added), diff)
    return diff


def update_notes(content: str) -> None:
    with open(NOTES_FILE, 'w') as f:
        f.write(content)
    log.info("notes.txt updated (%d characters)", len(content))


def load_prompt() -> str:
    with open(PROMPT_FILE, 'r') as f:
        prompt = f.read()
    log.debug("Loaded prompt from %s (%d characters)", PROMPT_FILE, len(prompt))
    return prompt


def call_llm(system_prompt: str, diff: str, today: str) -> list[dict]:
    with open(OTJ_CSV, 'r') as f:
        existing_csv = f.read()

    user_message = (
        f"Today's date: {today}\n\n"
        f"Existing OTJ CSV (for context on formatting):\n{existing_csv}\n\n"
        f"New activity content to log:\n{diff}"
    )

    log.info("Sending request to LLM (model: claude-haiku-4-5-20251001)")
    log.debug("User message sent to LLM:\n%s", user_message)

    message = anthropic_client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=2048,
        system=system_prompt,
        messages=[{"role": "user", "content": user_message}],
    )

    response_text = message.content[0].text.strip()
    log.debug("Raw LLM response:\n%s", response_text)

    if response_text.startswith("```"):
        response_text = response_text.split("\n", 1)[1].rsplit("```", 1)[0].strip()
        log.debug("Stripped markdown fences. Cleaned response:\n%s", response_text)

    rows = json.loads(response_text)
    log.info("LLM returned %d row(s) to write to CSV", len(rows))
    for i, row in enumerate(rows):
        log.debug("  Row %d: %s", i + 1, row)
    return rows


def append_to_csv(rows: list[dict]) -> None:
    log.info("Appending %d row(s) to %s", len(rows), OTJ_CSV)
    with open(OTJ_CSV, 'a', newline='') as f:
        writer = csv.writer(f)
        for i, row in enumerate(rows):
            writer.writerow([
                row['date'],
                row['time-spent'],
                row['start-time'],
                row['comments'],
                '',
            ])
            log.debug("  Wrote row %d: date=%s time-spent=%s start-time=%s comments=%r",
                      i + 1, row['date'], row['time-spent'], row['start-time'], row['comments'])


@app.route('/log-activities', methods=['POST'])
def log_activities():
    log.info("POST /log-activities received")

    data = request.get_json()
    if not data:
        msg = (
            "Request body is missing or not valid JSON. "
            "Expected: Content-Type: application/json with a JSON object body. "
            "Got: no parseable JSON. Ensure the client sets Content-Type: application/json."
        )
        log.warning(msg)
        return jsonify({"error": msg}), 400

    log.debug("Parsed request JSON: %s", data)

    content = data.get('content', '').strip()
    if not content:
        msg = (
            "The 'content' field is missing or empty. "
            "Expected: a non-empty string in the 'content' key of the JSON body. "
            f"Got: content={repr(data.get('content'))}. "
            "This field must contain the activity text to be logged."
        )
        log.warning(msg)
        return jsonify({"error": msg}), 400

    log.info("Content received (%d characters)", len(content))
    log.debug("Content:\n%s", content)

    diff = compute_diff(content)
    if diff is None:
        msg = (
            "No new content detected. "
            "The incoming 'content' field is identical to what was last processed in notes.txt. "
            "Nothing was written to the CSV. Send content that includes new lines to trigger logging."
        )
        log.info(msg)
        return jsonify({"status": "no new content", "detail": msg}), 200

    try:
        system_prompt = load_prompt()
    except FileNotFoundError:
        msg = (
            f"Prompt file not found at {PROMPT_FILE}. "
            "Expected: a file named 'llm_prompt.txt' in the same directory as otj-server.py. "
            "Create the file with the LLM system prompt and retry."
        )
        log.error(msg)
        return jsonify({"error": msg}), 500

    try:
        rows = call_llm(system_prompt, diff, today=date.today().isoformat())
    except json.JSONDecodeError as e:
        msg = (
            "The LLM returned a response that could not be parsed as JSON. "
            "Expected: a JSON array of row objects (e.g. [{\"date\": ..., \"comments\": ...}]). "
            f"Got a response that failed JSON parsing at: {e}. "
            "Check llm_prompt.txt to ensure the model is instructed to return only raw JSON."
        )
        log.error(msg)
        log.error("JSONDecodeError detail: %s", e)
        return jsonify({"error": msg}), 500
    except anthropic.AuthenticationError as e:
        msg = (
            "Anthropic API authentication failed. "
            "Expected: a valid ANTHROPIC_API_KEY set in the .env file. "
            f"Got: {e}. "
            "Check that ANTHROPIC_API_KEY is set correctly and the key is active."
        )
        log.error(msg)
        return jsonify({"error": msg}), 500
    except anthropic.RateLimitError as e:
        msg = (
            "Anthropic API rate limit hit. "
            "The API rejected the request because too many requests were made in a short period. "
            f"Got: {e}. Wait a moment and retry."
        )
        log.error(msg)
        return jsonify({"error": msg}), 429
    except Exception as e:
        msg = f"Unexpected error calling LLM: {type(e).__name__}: {e}"
        log.exception(msg)
        return jsonify({"error": msg}), 500

    try:
        append_to_csv(rows)
    except KeyError as e:
        msg = (
            f"LLM response is missing an expected field: {e}. "
            "Expected each row object to contain: 'date', 'time-spent', 'start-time', 'comments'. "
            f"Got rows: {rows}. "
            "Update llm_prompt.txt to enforce the correct output schema."
        )
        log.error(msg)
        return jsonify({"error": msg}), 500

    update_notes(content)

    log.info("Request complete — %d row(s) written to CSV", len(rows))
    return jsonify({"status": "ok", "rows_added": len(rows), "rows": rows}), 200


@app.route('/reset-notes', methods=['DELETE'])
def reset_notes():
    log.info("DELETE /reset-notes received")
    if not os.path.exists(NOTES_FILE):
        msg = (
            f"notes.txt does not exist at {NOTES_FILE} — nothing to delete. "
            "The file is created automatically on the first call to /log-activities."
        )
        log.warning(msg)
        return jsonify({"status": "not_found", "detail": msg}), 404

    os.remove(NOTES_FILE)
    log.info("notes.txt deleted — next call to /log-activities will treat all content as new")
    return jsonify({"status": "ok", "detail": "notes.txt deleted. The next /log-activities call will treat all content as new."}), 200

@app.route('/submit-otjs', methods=['POST'])
def submit_otjs():
    global _browser_driver

    data = request.get_json()
    if not data:
        msg = (
            "Request body is missing the MFA code. "
            "Expected: Content-Type: application/json with a JSON object body. "
            "Got: no parseable JSON. Ensure the client sets Content-Type: application/json."
        )
        log.warning(msg)
        return jsonify({"error": msg}), 400

    mfa_code = data.get('mfa_code', '').strip()

    with _browser_lock:
        driver = _browser_driver
        _browser_driver = None

    if driver is None:
        msg = "Browser is not ready yet — still navigating to the OTP page. Try again in a few seconds."
        log.warning(msg)
        return jsonify({"error": msg}), 503

    try:
        result = login_and_submit_otjs(driver, mfa_code)
    except Exception as e:
        log.exception("Error during OTJ submission")
        return jsonify({"error": str(e)}), 500
    finally:
        # Always start a fresh browser prep for the next request
        threading.Thread(target=_init_browser, daemon=True).start()

    return jsonify({"status": "ok", "detail": result}), 200


if __name__ == '__main__':
    log.info("Starting flask-server on 0.0.0.0:8945")
    app.run(host='0.0.0.0', port=8945)
