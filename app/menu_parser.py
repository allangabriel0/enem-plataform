"""
menu_parser.py — Parser do arquivo de menus de tags do Telegram.

Formato suportado:
    CANAL: NomeDoCanal

    = Nome_do_Curso
    == Nome_da_Seção
    #TAG01 #TAG02 #TAG03

Hierarquia resultante: Canal → Curso → Seção → lista de tags.
"""
import logging
import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.config import settings
from app.utils.text import clean_title

logger = logging.getLogger("enem")

# Tags de vídeo (#F001, #Doc01) e materiais (#Doc01 etc.)
TAG_PATTERN = re.compile(r"#[A-Za-z]+\d+")

# Mapeamento de palavras-chave (normalizadas) para nome canônico da matéria
_SUBJECT_MAP: dict[str, str] = {
    # Correspondências exatas ou por prefixo longo
    "filosofia": "Filosofia",
    "fil": "Filosofia",
    "sociologia": "Sociologia",
    "soc": "Sociologia",
    "portugues": "Português",
    "português": "Português",
    "port": "Português",
    "lingua": "Português",
    "linguaportuguesa": "Português",
    "matematica": "Matemática",
    "matemática": "Matemática",
    "mat": "Matemática",
    "historia": "História",
    "história": "História",
    "hist": "História",
    "geografia": "Geografia",
    "geo": "Geografia",
    "biologia": "Biologia",
    "bio": "Biologia",
    "fisica": "Física",
    "física": "Física",
    "fis": "Física",
    "quimica": "Química",
    "química": "Química",
    "qui": "Química",
    "ingles": "Inglês",
    "inglês": "Inglês",
    "ing": "Inglês",
    "espanhol": "Espanhol",
    "esp": "Espanhol",
    "artes": "Artes",
    "arte": "Artes",
    "redacao": "Redação",
    "redação": "Redação",
    "red": "Redação",
    "literatura": "Literatura",
    "lit": "Literatura",
    "enem": "ENEM",
    "atualidades": "Atualidades",
    "atual": "Atualidades",
}


# ---------------------------------------------------------------------------
# Tipos de dados
# ---------------------------------------------------------------------------

@dataclass
class MenuEntry:
    """Representa uma entrada do menu: canal → curso → seção → tags."""
    channel: str
    course: str
    section: str
    tags: list[str] = field(default_factory=list)
    subject: str = field(default="")

    def __post_init__(self) -> None:
        if not self.subject:
            self.subject = infer_subject(self.channel)


# Tipo de retorno de group_videos_for_dashboard
# canal → curso → seção → lista de vídeos
DashboardGroups = dict[str, dict[str, dict[str, list[Any]]]]


# ---------------------------------------------------------------------------
# Funções auxiliares
# ---------------------------------------------------------------------------

def _remove_accents(text: str) -> str:
    """Remove diacríticos de uma string Unicode."""
    return "".join(
        c for c in unicodedata.normalize("NFD", text)
        if unicodedata.category(c) != "Mn"
    )


def _normalize_key(name: str) -> str:
    """Normaliza para lookup: minúsculas, sem acentos, sem separadores."""
    return _remove_accents(name.lower().replace("_", "").replace(" ", "").replace("-", ""))


# ---------------------------------------------------------------------------
# API pública
# ---------------------------------------------------------------------------

def infer_subject(channel_name: str) -> str:
    """
    Infere a matéria a partir do nome do canal.

    Estratégia: normaliza o nome e procura match exato, depois por prefixo
    mais longo. Se nenhum match, retorna o próprio nome do canal.
    """
    key = _normalize_key(channel_name)

    # 1. Match exato
    if key in _SUBJECT_MAP:
        return _SUBJECT_MAP[key]

    # 2. Prefixo mais longo que seja chave válida
    best_key = ""
    for k in _SUBJECT_MAP:
        if key.startswith(k) and len(k) > len(best_key):
            best_key = k
    if best_key:
        return _SUBJECT_MAP[best_key]

    # 3. Sem match — retorna o nome original
    return channel_name


def extract_tag_from_text(text: str) -> str | None:
    """
    Extrai a primeira tag (#F001, #Doc01…) de um texto qualquer.
    Retorna None se não encontrar nenhuma.
    """
    match = TAG_PATTERN.search(text)
    return match.group(0) if match else None


def parse_menu_text(text: str) -> list[MenuEntry]:
    """
    Parseia o conteúdo do arquivo de menus e devolve uma lista de MenuEntry.

    Linhas reconhecidas:
        CANAL: Nome        → inicia novo canal
        = Nome_do_Curso    → inicia novo curso (reseta seção)
        == Nome_da_Seção   → inicia nova seção
        #TAG01 #TAG02 …    → tags do canal/curso/seção correntes
        linhas em branco   → ignoradas
    """
    entries: list[MenuEntry] = []
    current_channel = ""
    current_course = ""
    current_section = ""
    current_tags: list[str] = []

    def _commit() -> None:
        """Salva a entrada corrente se houver tags acumuladas."""
        if current_channel and current_tags:
            entries.append(
                MenuEntry(
                    channel=current_channel,
                    course=current_course,
                    section=current_section,
                    tags=list(current_tags),  # cópia — current_tags será limpo
                )
            )

    for raw_line in text.splitlines():
        line = raw_line.strip()

        # Ignora linhas vazias e linhas de comentário (# sem número de tag)
        if not line:
            continue
        if line.startswith("#") and not TAG_PATTERN.match(line):
            continue

        if line.startswith("CANAL:"):
            _commit()
            current_tags.clear()
            current_channel = line[len("CANAL:"):].strip()
            current_course = ""
            current_section = ""

        elif line.startswith("=="):
            # == deve ser checado ANTES de = para evitar falso-positivo
            _commit()
            current_tags.clear()
            current_section = clean_title(line.lstrip("=").strip())

        elif line.startswith("="):
            _commit()
            current_tags.clear()
            current_course = clean_title(line.lstrip("=").strip())
            current_section = ""

        else:
            # Linha de tags (pode ter múltiplas na mesma linha ou linhas seguidas)
            found = TAG_PATTERN.findall(line)
            if found:
                current_tags.extend(found)

    # Comita o último grupo ao final do arquivo
    _commit()

    logger.info("Menu parseado: %d entradas carregadas.", len(entries))
    return entries


def parse_menu_file(path: str | None = None) -> list[MenuEntry]:
    """
    Lê e parseia o arquivo de menus.
    Usa settings.MENU_FILE se nenhum path for fornecido.
    """
    file_path = Path(path or settings.MENU_FILE)
    if not file_path.exists():
        logger.warning("Arquivo de menus não encontrado: %s", file_path)
        return []
    text = file_path.read_text(encoding="utf-8")
    return parse_menu_text(text)


def match_menu_entry(
    tag: str,
    entries: list[MenuEntry],
    channel_name: str = "",
) -> MenuEntry | None:
    """
    Encontra a MenuEntry que contém a tag.

    Fallback em cascata quando há múltiplos candidatos:
      1. Canal exato
      2. Canal parcial (um nome contém o outro)
      3. Mesma matéria inferida
      4. Primeiro candidato encontrado
    """
    candidates = [e for e in entries if tag in e.tags]
    if not candidates:
        return None
    if len(candidates) == 1 or not channel_name:
        return candidates[0]

    channel_norm = _normalize_key(channel_name)

    # 1. Canal exato
    for entry in candidates:
        if _normalize_key(entry.channel) == channel_norm:
            return entry

    # 2. Canal parcial
    for entry in candidates:
        entry_norm = _normalize_key(entry.channel)
        if channel_norm in entry_norm or entry_norm in channel_norm:
            return entry

    # 3. Mesma matéria
    inferred = infer_subject(channel_name)
    for entry in candidates:
        if entry.subject == inferred:
            return entry

    # 4. Primeiro candidato
    return candidates[0]


def group_videos_for_dashboard(
    videos: list[Any],
    entries: list[MenuEntry],
) -> DashboardGroups:
    """
    Agrupa vídeos em canal → curso → seção para exibição no dashboard.

    As tags NÃO são globalmente únicas — cada canal tem seu próprio #F001,
    #F002 etc. O match correto usa (tag, canal_normalizado) como chave composta.

    Fallback em cascata quando não há match exato:
      1. Mesmo subject inferido (e.g. canal do Telegram bate com CANAL: do menu)
      2. telegram_group_name → course_name → lesson_name  (campos do Video)
      3. 'Outros' → 'Sem Categoria' → 'Sem Seção'
    """
    from collections import defaultdict

    # Índice: tag → lista de MenuEntry (para busca por candidatos)
    tag_candidates: dict[str, list[MenuEntry]] = defaultdict(list)
    for entry in entries:
        for t in entry.tags:
            tag_candidates[t].append(entry)

    # Índice composto: (tag, canal_normalizado) → MenuEntry  — lookup O(1)
    compound_index: dict[tuple[str, str], MenuEntry] = {}
    for entry in entries:
        canal_norm = _normalize_key(entry.channel)
        for t in entry.tags:
            key = (t, canal_norm)
            if key not in compound_index:
                compound_index[key] = entry

    result: DashboardGroups = {}

    for video in videos:
        tag = video.menu_tag or ""
        group_name = getattr(video, "telegram_group_name", "") or ""
        group_norm = _normalize_key(group_name)

        entry: MenuEntry | None = None

        if tag:
            # 1. Match exato: (tag, canal_normalizado)
            entry = compound_index.get((tag, group_norm))

            # 2. Fallback: mesmo subject (ex: canal Telegram ≠ nome no menu)
            if entry is None:
                inferred = infer_subject(group_name)
                for candidate in tag_candidates.get(tag, []):
                    if candidate.subject == inferred:
                        entry = candidate
                        break

            # 3. Fallback: primeiro candidato com a tag
            if entry is None:
                candidates = tag_candidates.get(tag, [])
                if candidates:
                    entry = candidates[0]

        if entry:
            channel = entry.channel
            course  = entry.course  or "Sem Curso"
            section = entry.section or "Sem Seção"
        else:
            channel = group_name or "Outros"
            course  = getattr(video, "course_name",  None) or "Sem Categoria"
            section = getattr(video, "lesson_name",  None) or "Sem Seção"

        result.setdefault(channel, {})
        result[channel].setdefault(course, {})
        result[channel][course].setdefault(section, [])
        result[channel][course][section].append(video)

    return result
