"""unit tests for loom.security.password_recovery."""

import re

from loom.security.password_recovery import (
    generate_codes,
    hash_code,
    parse,
    serialize,
    verify_and_consume,
)

_CODE_PATTERN = re.compile(r"^[0-9a-f]{5}-[0-9a-f]{5}-[0-9a-f]{5}-[0-9a-f]{5}$")


def test_generate_codes_returns_eight_codes() -> None:
    """generate_codes returns exactly 8 codes."""
    codes = generate_codes()
    assert len(codes) == 8


def test_generate_codes_each_matches_display_format() -> None:
    """every code is four hyphen-separated groups of 5 lowercase hex."""
    for code in generate_codes():
        assert _CODE_PATTERN.match(code), (
            f"code {code!r} does not match display format"
        )


def test_generate_codes_all_unique_within_one_call() -> None:
    """no two codes in a single batch are identical."""
    codes = generate_codes()
    assert len(set(codes)) == len(codes)


def test_hash_code_hyphenated_and_raw_produce_same_digest() -> None:
    """hash_code normalises hyphens away before hashing."""
    code = generate_codes()[0]
    raw = code.replace("-", "")
    assert hash_code(code) == hash_code(raw)


def test_hash_code_uppercase_produces_same_digest() -> None:
    """hash_code is case-insensitive."""
    code = generate_codes()[0]
    assert hash_code(code) == hash_code(code.upper())


def test_hash_code_mixed_case_hyphenated_same_as_raw_lowercase() -> None:
    """hyphenated, uppercase, and raw forms all resolve to one digest."""
    code = generate_codes()[0]
    raw_lower = code.replace("-", "")
    raw_upper = raw_lower.upper()
    hyphen_upper = code.upper()
    digest = hash_code(code)
    assert hash_code(raw_lower) == digest
    assert hash_code(raw_upper) == digest
    assert hash_code(hyphen_upper) == digest


def test_hash_code_ignores_whitespace() -> None:
    """spaces and tabs between groups are stripped before hashing."""
    code = generate_codes()[0]
    spaced = code.replace("-", " ")
    tabbed = code.replace("-", "\t")
    expected = hash_code(code)
    assert hash_code(spaced) == expected
    assert hash_code(tabbed) == expected


def test_hash_code_ignores_other_non_hex_characters() -> None:
    """any non-hex character is stripped, not treated as an error."""
    code = generate_codes()[0]
    # inject some punctuation that would appear in hand-transcription errors
    mangled = code[0:5] + "!" + code[5:]
    assert hash_code(mangled) == hash_code(code)


def test_serialize_and_parse_round_trip() -> None:
    """serialize then parse returns the original list unchanged."""
    codes = generate_codes()
    hashes = [hash_code(c) for c in codes]
    stored = serialize(hashes)
    assert parse(stored) == hashes


def test_parse_none_returns_empty_list() -> None:
    """parse(None) returns [] without raising."""
    assert parse(None) == []


def test_parse_empty_string_returns_empty_list() -> None:
    """parse('') returns []."""
    assert parse("") == []


def test_parse_filters_empty_fragments() -> None:
    """parse ignores trailing/leading commas that produce empty strings."""
    h = hash_code(generate_codes()[0])
    assert parse(f",{h},") == [h]


def test_verify_and_consume_returns_false_for_none_stored() -> None:
    """(False, None) when stored is None — no codes to match."""
    ok, remaining = verify_and_consume(None, generate_codes()[0])
    assert ok is False
    assert remaining is None


def test_verify_and_consume_returns_false_for_empty_stored() -> None:
    """(False, '') when stored is an empty string."""
    ok, remaining = verify_and_consume("", generate_codes()[0])
    assert ok is False
    assert remaining == ""


def test_verify_and_consume_returns_false_for_unknown_code() -> None:
    """wrong candidate leaves stored unchanged and returns False."""
    codes = generate_codes()
    hashes = [hash_code(c) for c in codes]
    stored = serialize(hashes)

    unknown = generate_codes()[0]  # fresh batch — distinct codes
    ok, remaining = verify_and_consume(stored, unknown)
    assert ok is False
    assert remaining == stored


def test_verify_and_consume_removes_matched_hash() -> None:
    """a matching code is consumed: remaining has exactly one fewer hash."""
    codes = generate_codes()
    hashes = [hash_code(c) for c in codes]
    stored = serialize(hashes)

    ok, remaining = verify_and_consume(stored, codes[0])
    assert ok is True
    assert len(parse(remaining)) == len(hashes) - 1


def test_verify_and_consume_does_not_remove_other_hashes() -> None:
    """only the matched hash is removed; all others are preserved."""
    codes = generate_codes()
    hashes = [hash_code(c) for c in codes]
    stored = serialize(hashes)

    ok, remaining = verify_and_consume(stored, codes[3])
    assert ok is True
    remaining_list = parse(remaining)
    # every hash except the consumed one should still be present
    for i, h in enumerate(hashes):
        if i == 3:
            assert h not in remaining_list
        else:
            assert h in remaining_list


def test_verify_and_consume_returns_none_remaining_on_last_code() -> None:
    """consuming the final code sets remaining to None (column becomes NULL)."""
    code = generate_codes()[0]
    stored = serialize([hash_code(code)])

    ok, remaining = verify_and_consume(stored, code)
    assert ok is True
    assert remaining is None


def test_verify_and_consume_rejects_already_consumed_code() -> None:
    """a code cannot be used twice (it is removed from stored on first use)."""
    codes = generate_codes()
    hashes = [hash_code(c) for c in codes]
    stored = serialize(hashes)

    _, remaining_after_first = verify_and_consume(stored, codes[0])
    ok, _ = verify_and_consume(remaining_after_first, codes[0])
    assert ok is False


def test_full_round_trip_generate_hash_serialize_parse_verify() -> None:
    """generate -> hash -> serialize -> parse -> verify_and_consume succeeds."""
    codes = generate_codes()
    hashes = [hash_code(c) for c in codes]
    stored = serialize(hashes)

    # parse and re-serialize should be an identity operation
    assert parse(stored) == hashes

    # verify the 5th code (arbitrary choice)
    ok, remaining = verify_and_consume(stored, codes[4])
    assert ok is True
    assert len(parse(remaining)) == 7
    assert hash_code(codes[4]) not in parse(remaining)
