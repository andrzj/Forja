"""The validators behind the detectors, one by one: where each of them says yes and where no.

The detectors only find candidates; these functions decide, so their edges decide what is masked.
"""

import pytest

from forja.core.redaction.pii import cnpj_valid, cpf_valid, email_valid, luhn_valid, phone_valid
from forja.core.redaction.rules import (
    _looks_like_a_secret_value,  # noqa: PLC2701 - the rule for generic credentials, tested alone
    is_placeholder,
    shannon_entropy,
)

# -- CPF and CNPJ ------------------------------------------------------------------------------


def test_a_cpf_needs_both_check_digits() -> None:
    assert cpf_valid("123.456.789-09")
    assert not cpf_valid("123.456.789-19")  # second digit wrong
    assert not cpf_valid("123.456.789-08")


def test_a_cpf_whose_first_check_digit_is_wrong_is_refused_even_if_the_second_fits_it() -> None:
    # 12345678917: the tenth digit should be 0; the eleventh is the right one for the wrong tenth.
    assert not cpf_valid("12345678917")


@pytest.mark.parametrize(
    "cnpj",
    [
        "63712926194145",
        "27724297124160",
        "71419357392560",
        "93246292148974",
        "76886543425986",
        "86852297363878",
    ],
)
def test_a_cnpj_is_checked_with_every_weight(cnpj: str) -> None:
    # Every digit of the base is non-zero, so a wrong weight anywhere changes a check digit.
    assert cnpj_valid(cnpj)
    wrong_last = cnpj[:-1] + str((int(cnpj[-1]) + 1) % 10)
    wrong_first_check = cnpj[:12] + str((int(cnpj[12]) + 1) % 10) + cnpj[13]
    assert not cnpj_valid(wrong_last)
    assert not cnpj_valid(wrong_first_check)


# -- payment cards -----------------------------------------------------------------------------


def test_a_card_has_between_13_and_19_digits() -> None:
    assert not luhn_valid("400000000002")  # 12 digits, Luhn-valid
    assert luhn_valid("4000000000006")  # 13
    assert luhn_valid("4000000000000000006")  # 19
    assert not luhn_valid("40000000000000000002")  # 20, Luhn-valid


def test_a_card_that_is_one_digit_repeated_is_not_a_card() -> None:
    assert not luhn_valid("4444 4444 4444 4444 4")  # Luhn-valid, 17 digits
    assert luhn_valid("2222222222224")  # two different digits is enough


def test_a_card_starts_with_a_digit_a_network_uses() -> None:
    assert luhn_valid("4111111111111111")
    assert luhn_valid("5500000000000004")
    assert luhn_valid("2000000000000006")  # lowest first digit
    assert luhn_valid("6000000000000007")  # highest first digit
    assert not luhn_valid("8000000000000003")
    assert not luhn_valid("1000000000000008")
    assert not luhn_valid("7000000000000005")


def test_a_card_fails_when_a_digit_is_off() -> None:
    assert not luhn_valid("4111111111111112")


# -- e-mail ------------------------------------------------------------------------------------


def test_the_domain_is_what_follows_the_last_at_sign() -> None:
    assert not email_valid("someone@host@example.com")
    assert email_valid("host@someone@company.com")


# -- phone -------------------------------------------------------------------------------------


def test_a_brazilian_number_in_international_form_is_checked_after_the_country_code() -> None:
    assert phone_valid("+55 13 98765-4321")  # mobile, 11 digits after 55
    assert phone_valid("+55 11 3456-7890")  # landline, 10 digits after 55
    assert not phone_valid("+55 11 456-7890")  # 9 digits
    assert not phone_valid("+55 10 98765-4321")  # no such area code


def test_leading_blanks_do_not_hide_the_plus_sign() -> None:
    assert phone_valid("  +55 11 98765-4321")


def test_other_countries_need_8_to_15_digits_and_no_leading_zero() -> None:
    assert not phone_valid("+1234567")  # 7
    assert phone_valid("+12345678")  # 8
    assert phone_valid("+123456789012345")  # 15
    assert not phone_valid("+1234567890123456")  # 16
    assert not phone_valid("+0123456789")


def test_a_national_number_is_10_or_11_digits_with_a_real_area_code() -> None:
    assert phone_valid("(11) 98765-4321")
    assert phone_valid("(11) 3456-7890")
    assert not phone_valid("(10) 98765-4321")
    assert not phone_valid("(11) 8765-432")


# -- generic credentials -----------------------------------------------------------------------


def test_an_empty_string_has_no_entropy() -> None:
    assert shannon_entropy("") == 0.0
    assert shannon_entropy("aaaa") == 0.0
    assert shannon_entropy("abcd") == 2.0


@pytest.mark.parametrize(
    "value",
    ["password", "secret", "undefined", "null"],
)
def test_documentation_values_are_placeholders(value: str) -> None:
    assert is_placeholder(value)
    assert is_placeholder(value.upper())


@pytest.mark.parametrize("value", ["********", "........", "--------", "_____", "00000000"])
def test_filler_is_a_placeholder(value: str) -> None:
    assert is_placeholder(value)


@pytest.mark.parametrize("value", ["[REDACTED:github-token:1]", "[PII:email:2]"])
def test_a_mask_made_by_forja_is_a_placeholder(value: str) -> None:
    assert is_placeholder(value)


@pytest.mark.parametrize("value", ["my-dummy-value1", "your-token", "your_token", "<token>"])
def test_a_value_with_a_placeholder_word_is_a_placeholder(value: str) -> None:
    assert is_placeholder(value)


def test_a_value_that_looks_real_is_not_a_placeholder() -> None:
    assert not is_placeholder("k8Jd9sLq2Vx")


@pytest.mark.parametrize("value", ["abc+def", "a/b", "tok=en", "pass!word", "a-b", "x@y", "p4ss"])
def test_a_value_with_a_digit_or_a_symbol_looks_like_a_secret(value: str) -> None:
    assert _looks_like_a_secret_value(value)


@pytest.mark.parametrize(
    "value", ["12345", "abcdef", "some_name", "some.name", "Name", "MaxValue", "XML"]
)
def test_a_plain_number_or_identifier_does_not(value: str) -> None:
    assert not _looks_like_a_secret_value(value)
