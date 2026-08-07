import os

# =====================================================================
# THE AI PROVIDER MODULES (The Decoupled LLM Adapters)
# =====================================================================

class GeminiProvider:
    def __init__(self, model_name="gemini-2.5-flash-preview-09-2025"):
        # Uses the modern google-genai library
        from google import genai
        self.client = genai.Client()
        self.model_name = model_name
        
    def generate(self, system_prompt, user_content, response_format=None):
        from google.genai import types
        config_args = {
            "system_instruction": system_prompt,
            "temperature": 0.7,
            "response_mime_type": "application/json"
        }
        if response_format:
            config_args["response_schema"] = response_format
            
        config = types.GenerateContentConfig(**config_args)
        response = self.client.models.generate_content(
            model=self.model_name, 
            contents=user_content,
            config=config
        )
        return response.text

class FeatherlessProvider:
    def __init__(self, model_name, api_key=None):
        from openai import OpenAI
        # Featherless matches standard OpenAI client specs
        self.client = OpenAI(
            base_url="https://api.featherless.tech/v1",
            api_key=api_key or os.environ.get("FEATHERLESS_API_KEY")
        )
        self.model_name = model_name
        
    def generate(self, system_prompt, user_content, response_format=None):
        if response_format:
            response = self.client.beta.chat.completions.parse(
                model=self.model_name,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_content}
                ],
                temperature=0.7,
                response_format=response_format
            )
            return response.choices[0].message.content
        else:
            response = self.client.chat.completions.create(
                model=self.model_name,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_content}
                ],
                temperature=0.7,
                response_format={"type": "json_object"}
            )
            return response.choices[0].message.content

class LocalProvider:
    def __init__(self, model_name="deepseek-r1:7b"):
        self.model_name = model_name

    def generate(self, system_prompt, user_content, response_format=None):
        import requests
        url = "http://localhost:11434/api/chat"
        payload = {
            "model": self.model_name,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content}
            ],
            "stream": False,
            "options": {
                "temperature": 0.3
            }
        }
        if response_format:
            payload["format"] = response_format.model_json_schema()
            
        res = requests.post(url, json=payload)
        res.raise_for_status()
        res_json = res.json()
        return res_json["message"]["content"]
