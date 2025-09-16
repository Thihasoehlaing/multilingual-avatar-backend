from typing import Dict

# Avatar morph targets you plan to drive (common set)
# AA=open (ah), O=round (oh), E=wide (ee), FV=teeth-on-lip, L=tongue, MBP=closed lips (m/b/p), WQ=rounded (w/oo), rest=neutral
_DEFAULT = "rest"

_POLLY_TO_MORPH: Dict[str, str] = {
    # Closures & labials
    "p": "MBP",   # m/b/p closed lips
    "b": "MBP",
    "m": "MBP",

    # Tongue/alveolar
    "t": "L",
    "d": "L",
    "l": "L",
    "n": "L",

    # Fricatives/affricates
    "f": "FV",
    "v": "FV",

    # Sibilants
    "s": "E",     # show teeth / slight smile
    "z": "E",
    "S": "WQ",    # "sh/zh" → more rounded
    "Z": "WQ",
    "tS": "WQ",   # "ch"
    "dZ": "WQ",   # "j"

    # Vowels (coarse mapping)
    "i": "E",     # ee
    "I": "E",
    "e": "E",
    "E": "AA",    # eh
    "a": "AA",    # ah
    "A": "AA",
    "o": "O",     # oh
    "O": "O",
    "u": "WQ",    # oo / rounded
    "U": "WQ",
    "@": "AA",    # schwa
}

def to_morph(viseme_value: str) -> str:
    """Map Polly viseme 'value' to your avatar morph target key."""
    return _POLLY_TO_MORPH.get(viseme_value, _DEFAULT)
