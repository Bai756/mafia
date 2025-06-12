import requests
import json

response = requests.post(
    'http://localhost:11434/api/generate',
    json={
        'model': 'mistral',
        'prompt': 'Generate a Mafia game argument accusing another player based on subtle clues.',
    }
)

text = ""
for line in response.text.splitlines():
    try:
        data = json.loads(line)
        text += data.get("response", "")
    except Exception:
        continue

print(text)