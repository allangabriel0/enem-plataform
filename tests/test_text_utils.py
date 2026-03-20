
from app.utils.text import clean_title, short_video_title


# ---------------------------------------------------------------------------
# clean_title
# ---------------------------------------------------------------------------

def test_clean_title_removes_underscores():
    """Underscores viram espaços; acentuação preservada."""
    assert clean_title("Aula_01_-_Introdução") == "Aula 01 - Introdução"


def test_clean_title_replaces_multiple_underscores():
    assert clean_title("Aula__Extra___Avançada") == "Aula Extra Avançada"


def test_clean_title_smart_capitalize_acronym_preserved():
    """Palavras já em MAIÚSCULAS (acrônimos) não são alteradas."""
    result = clean_title("Questões_de_ENEM")
    assert "ENEM" in result
    # "de" deve ficar minúsculo por ser preposição no meio
    assert " de " in result


def test_clean_title_smart_capitalize_small_words():
    """Preposições e artigos no meio do título ficam em minúsculo."""
    result = clean_title("Aula_de_Filosofia_e_Sociologia")
    assert result == "Aula de Filosofia e Sociologia"


def test_clean_title_smart_capitalize_first_word_always_upper():
    """Mesmo que a primeira palavra seja preposição, fica com maiúscula."""
    result = clean_title("de_onde_viemos")
    assert result.startswith("De")


def test_clean_title_empty_string():
    assert clean_title("") == ""


def test_clean_title_already_clean():
    """Título sem underscore e com capitalização correta é preservado."""
    title = "Aula 01 - Funções Quadráticas"
    assert clean_title(title) == title


def test_clean_title_collapses_spaces():
    assert clean_title("Aula  01   Introdução") == "Aula 01 Introdução"


def test_clean_title_various_acronyms():
    """USP, FUVEST, ENEM etc. preservados em maiúsculo."""
    result = clean_title("Redação_para_FUVEST_e_ENEM")
    assert "FUVEST" in result
    assert "ENEM" in result
    assert " e " in result


# ---------------------------------------------------------------------------
# short_video_title
# ---------------------------------------------------------------------------

def test_short_video_title_removes_course_prefix():
    """Remove o nome do curso do início do título."""
    result = short_video_title("Matemática - Aula 01 - Funções", "Matemática")
    assert result == "Aula 01 - Funções"


def test_short_video_title_removes_course_prefix_case_insensitive():
    """A remoção do prefixo de curso é case-insensitive."""
    result = short_video_title("matemática - Aula 02", "Matemática")
    assert "Aula 02" in result


def test_short_video_title_removes_tag_prefix():
    """Remove prefixo de tag tipo #F001 do início do título."""
    assert short_video_title("#F001 Aula") == "Aula"


def test_short_video_title_removes_tag_with_separator():
    """Remove tag seguida de separadores comuns (hífen, dois pontos)."""
    assert short_video_title("#P001 - Introdução à Redação") == "Introdução à Redação"
    assert short_video_title("#M001: Equações") == "Equações"


def test_short_video_title_removes_doc_tag_prefix():
    """Tags de material (#Doc01) também são removidas."""
    assert short_video_title("#Doc01 Apostila") == "Apostila"


def test_short_video_title_fallback_to_original():
    """Se a remoção da tag deixar o título vazio, retorna o original."""
    original = "#F001"
    result = short_video_title(original)
    assert result == original


def test_short_video_title_no_prefix_unchanged():
    """Título sem tag nem prefixo de curso é retornado sem alteração."""
    title = "Introdução à Filosofia"
    assert short_video_title(title) == title


def test_short_video_title_empty_string():
    assert short_video_title("") == ""


def test_short_video_title_tag_and_course_combined():
    """Remove tag primeiro, depois prefixo de curso."""
    result = short_video_title("#F001 Filosofia - Existencialismo", "Filosofia")
    assert result == "Existencialismo"
