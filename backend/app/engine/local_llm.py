import logging
import json
import re
from typing import Dict, Any, List
import httpx
from app.core.config import settings


class LocalLLM:
    """
    Optional helper for template fields the rules could not find. It talks only to an
    OpenAI-compatible server you host yourself (Ollama, llama.cpp, vLLM, LM Studio) at
    LOCAL_LLM_URL. It is off unless LOCAL_LLM_URL is set, and values it returns are kept
    only when they appear in the document text, so it cannot invent data.
    """

    @staticmethod
    def enabled() -> bool:
        return bool(settings.LOCAL_LLM_URL)

    @staticmethod
    async def fill_missing(text: str, fields: Dict[str, Dict[str, Any]], schema_fields: List[Dict[str, Any]]) -> List[str]:
        if not LocalLLM.enabled():
            return []
        missing = [f for f in schema_fields if fields.get(f["name"], {}).get("value") is None]
        if not missing:
            return []

        spec = "\n".join(f'- "{f["name"]}": {f.get("label", f["name"])} ({f.get("data_type", "text")})' for f in missing)
        prompt = (
            "Extract these fields from the document. Reply with only a JSON object mapping each field name "
            "to the exact text from the document, or null if it is not present. Do not guess.\n"
            f"Fields:\n{spec}\n\nDocument:\n{text[:settings.LOCAL_LLM_MAX_CHARS]}"
        )
        try:
            async with httpx.AsyncClient(timeout=settings.LOCAL_LLM_TIMEOUT) as client:
                res = await client.post(
                    settings.LOCAL_LLM_URL.rstrip("/") + "/chat/completions",
                    json={"model": settings.LOCAL_LLM_MODEL, "temperature": 0,
                          "messages": [{"role": "user", "content": prompt}]},
                )
                res.raise_for_status()
                content = res.json()["choices"][0]["message"]["content"]
        except Exception as e:
            logging.getLogger("idp.llm").warning("Local LLM unavailable: %s", e)
            return []

        m = re.search(r"\{.*\}", content, re.DOTALL)
        try:
            answers = json.loads(m.group(0)) if m else {}
        except json.JSONDecodeError:
            return []

        flat_text = re.sub(r"\s+", " ", text).lower()
        filled = []
        for f in missing:
            v = answers.get(f["name"])
            if v is None or str(v).strip() == "":
                continue
            v = str(v).strip()
            if re.sub(r"\s+", " ", v).lower() not in flat_text:
                continue  # not grounded in the document: discard
            filled.append(f["name"])
            fld = fields[f["name"]]
            fld.update({"value": v, "confidence": 0.7, "extraction_method": "local_llm",
                        "validation_error": "Found by local LLM; please verify."})
        return filled
