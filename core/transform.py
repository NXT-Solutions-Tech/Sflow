"""Execute Option+N transforms — Llama reshapes the selected text with the
user-configured prompt.

No voice recording involved. User selects text, hits Option+N, gets the
transform pasted back replacing the selection.
"""
from groq import Groq
from config import LLM_CLEANUP_MODEL, get_setting
from core.token_budget import max_tokens_for


_SYSTEM = """Eres un asistente que transforma texto según una instrucción dada.

Reglas críticas:
- Devuelve SOLO el texto transformado, sin comentarios ni explicaciones
- NO uses markdown a menos que la instrucción lo pida
- Preserva el idioma del original a menos que se pida traducir
- NO saludes ni te despidas"""


class TransformHandler:
    def __init__(self):
        self._client = None

    def _get_client(self) -> Groq:
        if self._client is None:
            from core.secrets import get_key
            key = get_key("GROQ_API_KEY")
            if not key:
                raise ValueError("GROQ_API_KEY not configured")
            self._client = Groq(api_key=key, timeout=10.0)
        return self._client

    def get_prompt(self, index: int) -> tuple[str, str]:
        """Return (label, prompt) for transform at index. Empty if out of range."""
        prompts = get_setting("transform_prompts", [])
        if 0 <= index < len(prompts):
            p = prompts[index]
            return p.get("label", f"Transform {index+1}"), p.get("prompt", "")
        return "", ""

    def run(self, index: int, selected_text: str) -> str:
        """Apply the transform at `index` to the selected_text. Returns new text."""
        if not selected_text:
            return selected_text
        _, prompt = self.get_prompt(index)
        if not prompt:
            return selected_text

        user_msg = f"INSTRUCCIÓN: {prompt}\n\nTEXTO:\n{selected_text}"
        try:
            completion = self._get_client().chat.completions.create(
                model=LLM_CLEANUP_MODEL,
                messages=[
                    {"role": "system", "content": _SYSTEM},
                    {"role": "user", "content": user_msg},
                ],
                temperature=0.3,
                # Un transform "expande esta idea" produce mucho mas texto que la
                # entrada; escala con user_msg y nunca baja del minimo historico.
                max_tokens=max_tokens_for(user_msg, floor=2000),
            )
            result = (completion.choices[0].message.content or "").strip()
            if result.startswith("```") and result.endswith("```"):
                result = result.strip("`").strip()
            return result or selected_text
        except Exception as e:
            print(f"transform {index} failed: {e}")
            return selected_text
