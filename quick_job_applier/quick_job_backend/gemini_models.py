import config
import google.generativeai as genai
 
MODEL_PRIORITY = [
    "gemini-2.5-pro",
    "gemini-2.5-flash",
    "gemini-2.5-flash-lite",
]
 
def configure_gemini():
    genai.configure(api_key=config.GEMINI_API_KEY)
 
def get_gemini_models() -> list[str]:
    configure_gemini()
    models = []
    for m in genai.list_models():
        if "generateContent" in m.supported_generation_methods:
            name = m.name.replace("models/", "")
            print(name)
            models.append(name)
    return models
 
def select_gemini_model(available: list[str]) -> str:
    for m in MODEL_PRIORITY:
        if m in available:
            return m
    return "gemini-2.5-flash-lite"  # safe default
 