"""
utils/text.py — Limpeza e normalização de títulos de vídeos.
"""
import logging
import re

logger = logging.getLogger("enem")

# Palavras que ficam em minúsculo no meio de um título (PT-BR)
_SMALL_WORDS: frozenset[str] = frozenset({
    "a", "à", "às", "ao", "aos", "as", "o", "os",
    "de", "da", "do", "das", "dos",
    "em", "no", "na", "nos", "nas",
    "por", "pelo", "pela", "pelos", "pelas",
    "para", "com", "sem", "sob", "sobre", "entre",
    "e", "ou", "mas", "que", "se", "é", "um", "uma",
})

# Prefixo de tag no início do título: #F001, #Doc01, etc.
_TAG_PREFIX_RE = re.compile(r"^#[A-Za-z]+\d+\s*[-–—:]?\s*")

_MULTI_SPACE_RE = re.compile(r"\s{2,}")


# ---------------------------------------------------------------------------
# Funções públicas
# ---------------------------------------------------------------------------

def clean_title(text: str) -> str:
    """
    Normaliza o título de um vídeo para exibição.

    - Substitui underscores por espaços
    - Colapsa múltiplos espaços
    - Smart capitalization:
        • Acrônimos já em MAIÚSCULAS (ENEM, USP, FUVEST) são preservados
        • Preposições e artigos no meio do título ficam em minúsculo
        • Demais palavras têm a primeira letra maiúscula
    """
    if not text:
        return ""

    text = text.replace("_", " ")
    text = _MULTI_SPACE_RE.sub(" ", text).strip()

    words = text.split(" ")
    result: list[str] = []
    for word in words:
        if not word:
            continue
        is_first = not result  # primeira palavra visível
        result.append(_smart_case(word, is_first))

    return " ".join(result)


def short_video_title(title: str, course_name: str = "") -> str:
    """
    Versão encurtada do título para listagens.

    Ordem de simplificação:
      1. Remove prefixo de tag   (#F001 Aula → Aula)
      2. Remove prefixo de curso (Matemática - Aula 01 → Aula 01)
      3. Fallback: retorna o título original se o resultado ficar vazio
    """
    if not title:
        return title

    result = title.strip()

    # 1. Remove prefixo de tag
    result = _TAG_PREFIX_RE.sub("", result).strip()

    # 2. Remove prefixo de curso (testa a versão bruta e a versão limpa)
    if course_name:
        for prefix in (course_name.strip(), clean_title(course_name)):
            if prefix and result.lower().startswith(prefix.lower()):
                result = result[len(prefix):].lstrip(" \t-–—:/").strip()
                break

    # 3. Fallback
    return result if result else title


# ---------------------------------------------------------------------------
# Helpers privados
# ---------------------------------------------------------------------------

def _smart_case(word: str, is_first: bool) -> str:
    """Capitalização inteligente para uma palavra isolada."""
    # Acrônimos em maiúsculas (> 1 char, todos uppercase) → preservar
    if len(word) > 1 and word.isupper():
        return word
    # Pequenas palavras no meio do título → minúsculo
    if not is_first and word.lower() in _SMALL_WORDS:
        return word.lower()
    # Demais → primeira letra maiúscula, resto preservado
    return word[0].upper() + word[1:] if word else word
