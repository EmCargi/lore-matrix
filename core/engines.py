import os

# =====================================================================
# THE AI PROVIDER MODULES (The Decoupled LLM Adapters)
# =====================================================================

from core.ollama import default_chain, post_json

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
    def __init__(self, model_name="deepseek-r1:7b", base_url=None):
        # deepseek-r1:7b lives on the thin client only. The big rig is the
        # primary engine; it serves the small L3-8B-Stheno model (fast + clean
        # structured output) for synthesis, while the requested model names the
        # thin-client fallback. Both overridable via env.
        self.model_name = model_name
        primary_model = os.environ.get(
            "OLLAMA_PRIMARY_MODEL",
            "hf.co/l3utterfly/L3-8B-Stheno-v3.2-gguf:Q8_0",
        )
        self.chain = default_chain(primary_model, model_name)

    def generate(self, system_prompt, user_content, response_format=None):
        def _payload(model):
            payload = {
                "model": model,
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
            return payload

        return post_json("/api/chat", _payload, self.chain)["message"]["content"]

    def generate_vision(self, system_prompt, user_content, image_path, response_format=None):
        """Multimodal generation — send a raw image to a vision-capable model.

        The big rig is the only node hosting a vision model (moondream:latest),
        so the chain is big-rig-first with the vision model on both slots; the
        thin client has no vision model, so a big-rig outage raises loudly
        rather than silently degrading to text-only OCR. The vision model is
        overridable via OLLAMA_VISION_MODEL.
        """
        import base64

        vision_model = os.environ.get("OLLAMA_VISION_MODEL", "moondream:latest")
        chain = default_chain(vision_model, vision_model)

        with open(image_path, "rb") as f:
            img_b64 = base64.b64encode(f.read()).decode("utf-8")

        def _payload(model):
            payload = {
                "model": model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_content, "images": [img_b64]},
                ],
                "stream": False,
                "options": {
                    "temperature": 0.3
                },
            }
            if response_format:
                payload["format"] = response_format.model_json_schema()
            return payload

        return post_json("/api/chat", _payload, chain)["message"]["content"]
