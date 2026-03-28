import os
import requests
import json

class TinyfishLLM:
    def __init__(self, api_key=None):
        self.api_key = api_key or os.getenv("TINYFISH_API_KEY", "")
        self.url = "https://agent.tinyfish.ai/v1/automation/run-sse"

    def invoke(self, prompt, goal="Extract the first 15 job postings. For each, get the full title text as shown on the page, the URL it links to, and the posting date. Return as JSON array with keys: title, url, posted."):
        headers = {
            "X-API-Key": self.api_key,
            "Content-Type": "application/json"
        }
        data = {
            "url": "https://news.ycombinator.com/jobs",
            "goal": goal,
            "prompt": prompt
        }
        response = requests.post(self.url, headers=headers, data=json.dumps(data), timeout=60)
        response.raise_for_status()
        return response.json()
