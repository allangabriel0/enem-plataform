"""
Testes para app/menu_parser.py.

Usa um trecho realista do formato raw_menus.txt como fixture.
"""
from unittest.mock import MagicMock

import pytest

from app.menu_parser import (
    MenuEntry,
    extract_tag_from_text,
    group_videos_for_dashboard,
    infer_subject,
    match_menu_entry,
    parse_menu_text,
)

# ---------------------------------------------------------------------------
# Fixture — trecho representativo do raw_menus.txt
# ---------------------------------------------------------------------------

SAMPLE_MENU = """\
CANAL: Filosofia

= Filosofia_Geral
== Introdução_à_Filosofia
#F001 #F002 #F003

== Ética_e_Política
#F004 #F005

= Filosofia_Contemporânea
== Existencialismo_e_Absurdo
#F010 #F011

CANAL: Português

= Redação
== Estrutura_da_Redação
#P001 #P002
#Doc01

== Tipos_de_Texto
#P003 #P004

= Literatura
== Modernismo_Brasileiro
#P010 #P011 #P012

CANAL: Matemática

= Álgebra
== Equações_do_2º_Grau
#M001 #M002 #M003

= Geometria
== Geometria_Plana
#M010 #M011
"""


@pytest.fixture()
def entries() -> list[MenuEntry]:
    return parse_menu_text(SAMPLE_MENU)


# ---------------------------------------------------------------------------
# parse_menu_text
# ---------------------------------------------------------------------------

def test_parse_menu_text_basic(entries: list[MenuEntry]):
    """Canal, curso, seção e tags são parseados corretamente."""
    # Primeira entry: Filosofia / Filosofia_Geral / Introdução_à_Filosofia
    first = entries[0]
    assert first.channel == "Filosofia"
    assert first.course == "Filosofia_Geral"
    assert first.section == "Introdução_à_Filosofia"
    assert "#F001" in first.tags
    assert "#F002" in first.tags
    assert "#F003" in first.tags
    # Subject inferida automaticamente
    assert first.subject == "Filosofia"


def test_parse_menu_text_multiple_courses(entries: list[MenuEntry]):
    """Múltiplos cursos no mesmo canal são parseados como entries distintas."""
    filosofia_entries = [e for e in entries if e.channel == "Filosofia"]
    courses = {e.course for e in filosofia_entries}
    assert "Filosofia_Geral" in courses
    assert "Filosofia_Contemporânea" in courses


def test_parse_menu_text_multiple_tag_lines(entries: list[MenuEntry]):
    """Tags em linhas consecutivas (sem nova seção) pertencem à mesma seção."""
    # Seção Estrutura_da_Redação tem #P001, #P002 e #Doc01 em linhas separadas
    redacao = next(
        e for e in entries
        if e.section == "Estrutura_da_Redação"
    )
    assert "#P001" in redacao.tags
    assert "#P002" in redacao.tags
    assert "#Doc01" in redacao.tags


def test_parse_menu_text_total_entries(entries: list[MenuEntry]):
    """Número total de entries bate com as seções do SAMPLE_MENU."""
    # Filosofia: 3 seções × canal + Português: 3 seções + Matemática: 2 seções = 8
    assert len(entries) == 8


# ---------------------------------------------------------------------------
# infer_subject
# ---------------------------------------------------------------------------

def test_infer_subject_portugues():
    """'Português' com acento e variações devem mapear para 'Português'."""
    assert infer_subject("Português") == "Português"
    assert infer_subject("Port") == "Português"
    assert infer_subject("Portugues") == "Português"
    assert infer_subject("Lingua_Portuguesa") == "Português"


def test_infer_subject_matematica():
    assert infer_subject("Matemática") == "Matemática"
    assert infer_subject("Mat") == "Matemática"
    assert infer_subject("Matematica_Basica") == "Matemática"


def test_infer_subject_historia():
    assert infer_subject("História") == "História"
    assert infer_subject("Hist") == "História"


def test_infer_subject_unknown_returns_name():
    """Canal desconhecido retorna o próprio nome do canal."""
    assert infer_subject("Canal_Desconhecido") == "Canal_Desconhecido"
    assert infer_subject("XYZ123") == "XYZ123"


# ---------------------------------------------------------------------------
# match_menu_entry
# ---------------------------------------------------------------------------

def test_match_menu_entry_exact_channel(entries: list[MenuEntry]):
    """Match por canal exato retorna a entry correta."""
    entry = match_menu_entry("#F001", entries, channel_name="Filosofia")
    assert entry is not None
    assert entry.channel == "Filosofia"
    assert "#F001" in entry.tags


def test_match_menu_entry_no_channel_returns_first(entries: list[MenuEntry]):
    """Sem channel_name, retorna o primeiro candidato encontrado."""
    entry = match_menu_entry("#M001", entries)
    assert entry is not None
    assert "#M001" in entry.tags


def test_match_menu_entry_fallback_subject(entries: list[MenuEntry]):
    """Fallback por matéria: canal 'Port' deve encontrar entry de Português."""
    # Adiciona uma entry duplicada de outro canal para forçar o fallback
    extra = MenuEntry(channel="FilosofiaExtra", course="C", section="S", tags=["#P001"])
    augmented = list(entries) + [extra]

    entry = match_menu_entry("#P001", augmented, channel_name="Port")
    assert entry is not None
    # Deve escolher a entry cujo subject seja 'Português'
    assert entry.subject == "Português"


def test_match_menu_entry_no_tag_returns_none(entries: list[MenuEntry]):
    """Tag inexistente retorna None."""
    result = match_menu_entry("#INEXISTENTE999", entries)
    assert result is None


def test_match_menu_entry_partial_channel(entries: list[MenuEntry]):
    """Match parcial de canal: 'Filosofia_2025' bate em 'Filosofia'."""
    entry = match_menu_entry("#F010", entries, channel_name="Filosofia_2025")
    assert entry is not None
    assert entry.channel == "Filosofia"


# ---------------------------------------------------------------------------
# extract_tag_from_text
# ---------------------------------------------------------------------------

def test_extract_tag_from_text():
    assert extract_tag_from_text("Aula sobre lógica #F001 continuação") == "#F001"
    assert extract_tag_from_text("Material de apoio #Doc01") == "#Doc01"


def test_extract_tag_from_text_first_only():
    """Retorna apenas a PRIMEIRA tag quando há múltiplas."""
    assert extract_tag_from_text("#P010 #P011 #P012") == "#P010"


def test_extract_tag_from_text_none():
    assert extract_tag_from_text("Texto sem nenhuma tag") is None
    assert extract_tag_from_text("") is None


# ---------------------------------------------------------------------------
# group_videos_for_dashboard
# ---------------------------------------------------------------------------

def _make_video(menu_tag: str, group_name: str = "Filosofia") -> MagicMock:
    v = MagicMock()
    v.menu_tag = menu_tag
    v.telegram_group_name = group_name
    v.course_name = None
    v.lesson_name = None
    return v


def test_group_videos_for_dashboard(entries: list[MenuEntry]):
    """Vídeos com tag mapeada são agrupados por canal/curso/seção."""
    v1 = _make_video("#F001")  # Filosofia / Filosofia_Geral / Introdução_à_Filosofia
    v2 = _make_video("#F002")  # mesmo grupo
    v3 = _make_video("#P001")  # Português / Redação / Estrutura_da_Redação

    result = group_videos_for_dashboard([v1, v2, v3], entries)

    assert "Filosofia" in result
    assert "Português" in result

    fil_courses = result["Filosofia"]
    assert "Filosofia_Geral" in fil_courses
    section_videos = fil_courses["Filosofia_Geral"]["Introdução_à_Filosofia"]
    assert v1 in section_videos
    assert v2 in section_videos

    port_section = result["Português"]["Redação"]["Estrutura_da_Redação"]
    assert v3 in port_section


def test_group_videos_for_dashboard_unmapped(entries: list[MenuEntry]):
    """Vídeo sem tag mapeada vai para o grupo do telegram_group_name."""
    v = _make_video(menu_tag="", group_name="Canal_Proprio")
    v.course_name = "Curso_X"
    v.lesson_name = "Lição_Y"

    result = group_videos_for_dashboard([v], entries)

    assert "Canal_Proprio" in result
    assert "Curso_X" in result["Canal_Proprio"]
    assert "Lição_Y" in result["Canal_Proprio"]["Curso_X"]


def test_group_videos_for_dashboard_empty(entries: list[MenuEntry]):
    """Lista vazia de vídeos retorna dict vazio."""
    assert group_videos_for_dashboard([], entries) == {}
