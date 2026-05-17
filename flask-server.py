import csv
import json
import os
from datetime import date
from difflib import unified_diff

import anthropic
from dotenv import load_dotenv
from flask import Flask, jsonify, request

load_dotenv()

app = Flask(__name__)

NOTES_FILE = os.path.join(os.path.dirname(__file__), 'notes.txt')
OTJ_CSV    = os.path.join(os.path.dirname(__file__), 'otjs.csv')
PROMPT_FILE = os.path.join(os.path.dirname(__file__), 'llm_prompt.txt')

anthropic_client = anthropic.Anthropic(api_key=os.getenv('ANTHROPIC_API_KEY'))


def compute_diff(new_content: str) -> str | None:
    if not os.path.exists(NOTES_FILE):
        with open(NOTES_FILE, 'w') as f:
            f.write(new_content)
        return new_content

    with open(NOTES_FILE, 'r') as f:
        old_content = f.read()

    old_lines = old_content.splitlines(keepends=True)
    new_lines = new_content.splitlines(keepends=True)

    added = [
        line[1:]
        for line in unified_diff(old_lines, new_lines, n=0)
        if line.startswith('+') and not line.startswith('+++')
    ]

    return ''.join(added) if added else None


def update_notes(content: str) -> None:
    with open(NOTES_FILE, 'w') as f:
        f.write(content)


def load_prompt() -> str:
    with open(PROMPT_FILE, 'r') as f:
        return f.read()


def call_llm(system_prompt: str, diff: str, today: str) -> list[dict]:
    with open(OTJ_CSV, 'r') as f:
        existing_csv = f.read()

    user_message = (
        f"Today's date: {today}\n\n"
        f"Existing OTJ CSV (for context on formatting):\n{existing_csv}\n\n"
        f"New activity content to log:\n{diff}"
    )

    message = anthropic_client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=2048,
        system=system_prompt,
        messages=[{"role": "user", "content": user_message}],
    )
    response_text = message.content[0].text.strip()
    return json.loads(response_text)


def append_to_csv(rows: list[dict]) -> None:
    with open(OTJ_CSV, 'a', newline='') as f:
        writer = csv.writer(f)
        for row in rows:
            writer.writerow([
                row['date'],
                row['time-spent'],
                row['start-time'],
                row['comments'],
                'False',
            ])


@app.route('/log-activities', methods=['POST'])
def log_activities():
    data = request.get_json()

    if not data:
        return jsonify({"error": "No JSON body"}), 400

    content = data.get('content', '').strip()
    if not content:
        return jsonify({"error": "No content provided"}), 400

    diff = compute_diff(content)
    if diff is None:
        return jsonify({"status": "no new content"}), 200

    try:
        system_prompt = load_prompt()
        rows = call_llm(system_prompt, diff, today=date.today().isoformat())
    except json.JSONDecodeError as e:
        return jsonify({"error": "LLM returned invalid JSON", "detail": str(e)}), 500
    except Exception as e:
        return jsonify({"error": str(e)}), 500

    append_to_csv(rows)
    update_notes(content)

    return jsonify({"status": "ok", "rows_added": len(rows)}), 200


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8945)
