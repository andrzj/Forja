import random

import pytest

from forja.core.redaction import ItemKind, PackageItem, Redactor, cnpj_valid, cpf_valid, luhn_valid
from forja.core.redaction.pii import email_valid, phone_valid
from tests.core.redaction.corpus import make_card, make_cnpj, make_cpf, personal_data, spaced

PERSONAL = personal_data()


def out(text: str) -> str:
    return Redactor().redact([PackageItem(ItemKind.TEXT, "note", text)]).items[0].content


# -- the validators ----------------------------------------------------------------------------


def test_generated_documents_are_valid_and_one_wrong_digit_makes_them_invalid() -> None:
    rng = random.Random(3)
    for _ in range(50):
        cpf, cnpj, card = make_cpf(rng), make_cnpj(rng), make_card(rng)
        assert cpf_valid(cpf) and cnpj_valid(cnpj) and luhn_valid(card)
        for text, check in ((cpf, cpf_valid), (cnpj, cnpj_valid), (card, luhn_valid)):
            last = int(text[-1])
            assert not check(text[:-1] + str((last + 1) % 10))


@pytest.mark.parametrize("text", ["11111111111", "000.000.000-00", "123.456.789-00", "1234567890"])
def test_numbers_that_look_like_a_cpf_but_are_not_one(text: str) -> None:
    assert not cpf_valid(text)


@pytest.mark.parametrize("text", ["00000000000000", "12.345.678/0001-00", "1234"])
def test_numbers_that_look_like_a_cnpj_but_are_not_one(text: str) -> None:
    assert not cnpj_valid(text)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("maria@empresa.com.br", True),
        ("a.b+tag@sub.domain.org", True),
        ("user@example.com", False),
        ("user@mail.example.org", False),
        ("ops@service.test", False),
        ("me@localhost", False),
        ("x@host.local", False),
        ("git@github.com", False),
        ("ssh@server.net", False),
    ],
)
def test_which_emails_identify_someone(text: str, expected: bool) -> None:
    assert email_valid(text) is expected


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("(11) 98765-4321", True),
        ("(21) 3456-7890", True),
        ("+55 11 98765-4321", True),
        ("11 98765-4321", True),
        ("+14155552671", True),
        ("(00) 98765-4321", False),  # no such area code
        ("(10) 98765-4321", False),
        ("+55 00 98765-4321", False),
        ("+0123456789", False),
    ],
)
def test_phone_numbers_need_a_real_area_code(text: str, expected: bool) -> None:
    assert phone_valid(text) is expected


# -- finding them in text ----------------------------------------------------------------------


@pytest.mark.parametrize("datum", PERSONAL, ids=lambda d: f"{d.kind}:{d.value[:6]}")
def test_each_kind_of_personal_data_is_masked_with_its_own_mask(datum) -> None:  # type: ignore[no-untyped-def]
    content = out(datum.text.format(value=datum.value))

    assert datum.value not in content
    assert f"[PII:{datum.kind}:1]" in content


def test_the_same_person_gets_the_same_mask_and_another_person_the_next_number() -> None:
    rng = random.Random(5)
    first, second = make_cpf(rng), make_cpf(rng)

    content = out(f"a {first}\nb {second}\nc {first}")

    assert content == "a [PII:cpf:1]\nb [PII:cpf:2]\nc [PII:cpf:1]"


def test_secret_and_personal_numbering_are_kept_apart() -> None:
    rng = random.Random(6)
    cpf = make_cpf(rng)

    assert out(f"{cpf} and token = Qx81Zp0LmN4vKa").count("[PII:cpf:1]") == 1


def test_unformatted_documents_are_found_but_longer_digit_runs_are_not() -> None:
    rng = random.Random(8)
    bare = make_cpf(rng, formatted=False)

    assert out(f"id {bare} ok") == "id [PII:cpf:1] ok"
    assert out(f"id 9{bare} ok") == f"id 9{bare} ok"  # twelve digits: not a CPF
    assert out(f"id {bare}9 ok") == f"id {bare}9 ok"


def test_cards_are_found_with_spaces_and_dashes_but_only_if_they_pass_luhn() -> None:
    rng = random.Random(9)
    card = make_card(rng)
    dashed = "-".join(card[i : i + 4] for i in range(0, 16, 4))

    assert out(f"pan {spaced(card)}") == "pan [PII:card:1]"
    assert out(f"pan {dashed}") == "pan [PII:card:1]"
    broken = card[:-1] + str((int(card[-1]) + 1) % 10)
    assert out(f"pan {broken}") == f"pan {broken}"


def test_a_cpf_and_a_phone_are_not_mixed_up() -> None:
    rng = random.Random(10)
    cpf = make_cpf(rng)

    # one number per distinct value in the category, whatever its kind
    assert out(f"cpf {cpf} tel (11) 98765-4321") == "cpf [PII:cpf:1] tel [PII:phone:2]"


def test_ordinary_numbers_survive() -> None:
    text = "1.2.3.4 | 2026-10-10 | 192.168.0.1 | 3.14159265 | 0x7ffe1234abcd | 1234-5678"

    assert out(text) == text
