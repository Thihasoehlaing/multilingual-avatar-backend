from fastapi import APIRouter
from pydantic import BaseModel
from typing import List
from app.utils.response import success

router = APIRouter()

class Language(BaseModel):
    code: str
    label: str

# 🔹 Current languages: Transcribe-supported + Malay
#   (For now, we’ll treat this as Polly’s set + Malay)
CURRENT_LANGUAGES: List[Language] = [
    Language(code="ms-MY", label="Malay (MY)"),
    Language(code="en-US", label="English (US)"),
    Language(code="en-AU", label="English (Australian)"),
    Language(code="en-GB", label="English (British)"),
    Language(code="en-IN", label="English (Indian)"),
    Language(code="en-NZ", label="English (New Zealand)"),
    Language(code="en-SG", label="English (Singaporean)"),
    Language(code="en-ZA", label="English (South African)"),
    Language(code="en-GB-WLS", label="English (Welsh)"),
    Language(code="arb", label="Arabic"),
    Language(code="ar-AE", label="Arabic (Gulf)"),
    Language(code="ca-ES", label="Catalan"),
    Language(code="yue-CN", label="Chinese (Cantonese)"),
    Language(code="cmn-CN", label="Chinese (Mandarin)"),
    Language(code="cs-CZ", label="Czech"),
    Language(code="da-DK", label="Danish"),
    Language(code="nl-BE", label="Dutch (Belgian)"),
    Language(code="nl-NL", label="Dutch"),
    Language(code="fi-FI", label="Finnish"),
    Language(code="fr-FR", label="French"),
    Language(code="fr-BE", label="French (Belgian)"),
    Language(code="fr-CA", label="French (Canadian)"),
    Language(code="hi-IN", label="Hindi"),
    Language(code="de-DE", label="German"),
    Language(code="de-AT", label="German (Austrian)"),
    Language(code="de-CH", label="German (Swiss standard)"),
    Language(code="is-IS", label="Icelandic"),
    Language(code="it-IT", label="Italian"),
    Language(code="ja-JP", label="Japanese"),
    Language(code="ko-KR", label="Korean"),
    Language(code="nb-NO", label="Norwegian"),
    Language(code="pl-PL", label="Polish"),
    Language(code="pt-BR", label="Portuguese (Brazilian)"),
    Language(code="pt-PT", label="Portuguese (European)"),
    Language(code="ro-RO", label="Romanian"),
    Language(code="ru-RU", label="Russian"),
    Language(code="es-ES", label="Spanish (Spain)"),
    Language(code="es-MX", label="Spanish (Mexican)"),
    Language(code="es-US", label="Spanish (US)"),
    Language(code="sv-SE", label="Swedish"),
    Language(code="tr-TR", label="Turkish"),
    Language(code="cy-GB", label="Welsh"),
]

# 🔹 Target languages = Polly-supported only (same list, minus Malay)
TARGET_LANGUAGES: List[Language] = [
    lang for lang in CURRENT_LANGUAGES if lang.code != "ms-MY"
]

@router.get("/current")
def get_current_languages():
    """Return available current languages (includes Malay)."""
    return success(data=[lang.dict() for lang in CURRENT_LANGUAGES])

@router.get("/target")
def get_target_languages():
    """Return available target languages (Polly supported only)."""
    return success(data=[lang.dict() for lang in TARGET_LANGUAGES])
