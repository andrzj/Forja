"""Synthetic secrets and personal data, built at run time from fragments.

Forja passes its own secret gate, so no complete secret-looking string may sit in the repository.
Every value here is assembled from pieces, with a seeded generator, so the test data is both
reproducible and invisible to a scanner reading the source.
"""

import random
import string
from collections.abc import Callable
from dataclasses import dataclass

ALNUM = string.ascii_letters + string.digits
BASE64 = ALNUM + "+/"
URLSAFE = ALNUM + "-_"
UPPER_B32 = "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567"
WORD = ALNUM + "_"


def pick(rng: random.Random, alphabet: str, length: int) -> str:
    """Random text that always mixes character classes, so its entropy is realistic."""
    body = [rng.choice(alphabet) for _ in range(length)]
    digits = [c for c in alphabet if c.isdigit()] or list(string.digits)
    uppers = [c for c in alphabet if c.isupper()] or list(string.ascii_uppercase)
    body[0], body[-1] = rng.choice(digits), rng.choice(uppers)
    return "".join(body)


@dataclass(frozen=True)
class Planted:
    """A snippet of text and the secret inside it."""

    rule: str
    text: str
    secret: str


def _plant(rule: str, template: str, secret: str) -> Planted:
    return Planted(rule, template.format(secret=secret), secret)


def secrets(seed: int = 7) -> list[Planted]:
    rng = random.Random(seed)
    pem_body = "\n".join(pick(rng, BASE64, 64) for _ in range(6))
    return [
        _plant("aws-access-key", "key = {secret}", "AK" + "IA" + pick(rng, UPPER_B32, 16)),
        _plant(
            "aws-secret-key",
            'aws_secret_access_key = "{secret}"',
            pick(rng, BASE64, 40),
        ),
        _plant("github-token", "token: {secret}", "gh" + "p_" + pick(rng, ALNUM, 36)),
        _plant(
            "github-fine-grained-token",
            "pat={secret}",
            "github" + "_pat_" + pick(rng, WORD, 40),
        ),
        _plant("gitlab-token", "x {secret} y", "gl" + "pat-" + pick(rng, URLSAFE, 24)),
        _plant("slack-token", "x {secret} y", "xo" + "xb-" + "1" * 10 + "-" + pick(rng, ALNUM, 24)),
        _plant("stripe-key", "x {secret} y", "sk_" + "live_" + pick(rng, ALNUM, 28)),
        _plant("google-api-key", "x {secret} y", "AI" + "za" + pick(rng, URLSAFE, 35)),
        _plant(
            "azure-storage-key",
            "DefaultEndpointsProtocol=https;Account" + "Key={secret}",
            pick(rng, BASE64, 86) + "==",
        ),
        _plant("npm-token", "x {secret} y", "npm" + "_" + pick(rng, ALNUM, 36)),
        _plant("pypi-token", "x {secret} y", "py" + "pi-AgEIcHlwaS5vcmc" + pick(rng, URLSAFE, 60)),
        _plant("anthropic-key", "x {secret} y", "sk-" + "ant-" + pick(rng, URLSAFE, 48)),
        _plant("openai-key", "x {secret} y", "sk-" + "proj-" + pick(rng, ALNUM, 48)),
        _plant(
            "jwt",
            "x {secret} y",
            "ey"
            + "J"
            + pick(rng, URLSAFE, 24)
            + ".ey"
            + "J"
            + pick(rng, URLSAFE, 24)
            + "."
            + pick(rng, URLSAFE, 30),
        ),
        _plant(
            "private-key-block",
            "-----BEGIN RSA PRIVATE" + " KEY-----\n{secret}\n-----END RSA PRIVATE" + " KEY-----",
            pem_body,
        ),
        _plant(
            "url-credentials",
            "DATABASE_URL=postgres://app:{secret}@db.internal:5432/app",
            pick(rng, ALNUM, 18),
        ),
        _plant(
            "connection-string-password",
            "Server=db;Database=app;User Id=sa;Pass" + "word={secret};Encrypt=true",
            pick(rng, ALNUM, 14),
        ),
        _plant(
            "authorization-header",
            "Authorization: Be" + "arer {secret}",
            pick(rng, URLSAFE, 40),
        ),
        _plant("generic-credential", 'api_key = "{secret}"', pick(rng, ALNUM, 32)),
    ]


# -- personal data -----------------------------------------------------------------------------


def _check_digit(digits: list[int], weights: list[int]) -> int:
    total = sum(d * w for d, w in zip(digits, weights, strict=True))
    rest = total % 11
    return 0 if rest < 2 else 11 - rest


def make_cpf(rng: random.Random, formatted: bool = True) -> str:
    base = [rng.randint(0, 9) for _ in range(9)]
    if len(set(base)) == 1:
        base[0] = (base[0] + 1) % 10
    base.append(_check_digit(base, list(range(10, 1, -1))))
    base.append(_check_digit(base, list(range(11, 1, -1))))
    digits = "".join(map(str, base))
    return f"{digits[:3]}.{digits[3:6]}.{digits[6:9]}-{digits[9:]}" if formatted else digits


def make_cnpj(rng: random.Random, formatted: bool = True) -> str:
    base = [rng.randint(0, 9) for _ in range(8)] + [0, 0, 0, 1]
    base.append(_check_digit(base, [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]))
    base.append(_check_digit(base, [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]))
    digits = "".join(map(str, base))
    if not formatted:
        return digits
    return f"{digits[:2]}.{digits[2:5]}.{digits[5:8]}/{digits[8:12]}-{digits[12:]}"


def make_card(rng: random.Random, prefix: str = "4") -> str:
    digits = [int(c) for c in prefix] + [rng.randint(0, 9) for _ in range(15 - len(prefix))]
    total = 0
    for index, value in enumerate(reversed(digits)):
        doubled = value * 2 if index % 2 == 0 else value
        total += doubled - 9 if doubled > 9 else doubled
    digits.append((10 - total % 10) % 10)
    return "".join(map(str, digits))


def spaced(card: str) -> str:
    return " ".join(card[i : i + 4] for i in range(0, 16, 4))


@dataclass(frozen=True)
class PlantedPii:
    kind: str
    text: str
    value: str


def personal_data(seed: int = 11) -> list[PlantedPii]:
    rng = random.Random(seed)
    cpf, cnpj, card = make_cpf(rng), make_cnpj(rng), make_card(rng)
    return [
        PlantedPii("cpf", "titular: {value}", cpf),
        PlantedPii("cpf", "cpf={value}", make_cpf(rng, formatted=False)),
        PlantedPii("cnpj", "empresa {value}", cnpj),
        PlantedPii("cnpj", "cnpj={value}", make_cnpj(rng, formatted=False)),
        PlantedPii("email", "contato: {value}", "maria.silva" + "@" + "empresa.com.br"),
        PlantedPii("email", "to <{value}>", "joao_pereira+nf" + "@" + "mail.corp.example.io"),
        PlantedPii("phone", "tel {value}", "(11) 98765-4321"),
        PlantedPii("phone", "tel {value}", "+55 21 99876-5432"),
        PlantedPii("phone", "tel {value}", "11 98765-4321"),
        PlantedPii("phone", "tel {value}", "+14155552671"),
        PlantedPii("card", "pan {value}", card),
        PlantedPii("card", "pan {value}", spaced(make_card(rng, "5"))),
    ]


# -- text that must be left exactly as it is ----------------------------------------------------

INNOCENT: list[tuple[str, str]] = [
    ("version", "requires-python >= 3.12.4 and pydantic 2.7.1, build 20261010.3"),
    ("timestamp", "created_at_ms = 1700000000000"),
    ("short id", "order 12345678 shipped"),
    ("uuid", "id = 123e4567-e89b-12d3-a456-426614174000"),
    ("git sha", "commit " + "a" * 40),
    ("ssh remote", "origin git@github.com:org/repo.git"),
    ("reserved mail", "write to user@example.com or ops@service.test or me@localhost"),
    ("npm scope", "import x from '@scope/package'"),
    ("expiry", "token_expiry_seconds = 3600"),
    ("call", "password = get_password()"),
    ("env ref", "api_key: ${API_KEY}"),
    ("template", "secret = {{ vault.secret }}"),
    ("identifier", "secret_name = some_long_identifier_name"),
    ("number", "SECRET_KEY_LENGTH = 1234567890"),
    ("doc key", "key = AKIAIOSFODNN7" + "EXAMPLE"),
    ("filler", 'password = "changeme" and api_key = "your-api-key-here"'),
    ("x filler", "token = xxxxxxxxxxxxxxxx"),
    ("invalid cpf", "ref 111.111.111-11 and 123.456.789-00"),
    ("dotted numbers", "ip 192.168.100.200 and 10.0.0.1/24"),
    ("phone-like id", "ticket 4155-5526"),
    ("code", "def authorize(token: str) -> bool:\n    return token == self.token"),
]


Generator = Callable[[random.Random], str]
