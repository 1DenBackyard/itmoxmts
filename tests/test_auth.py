from specguard.auth import hash_password, verify_password


def test_password_roundtrip() -> None:
    encoded = hash_password("secret")
    assert verify_password("secret", encoded)
    assert not verify_password("wrong", encoded)


def test_malformed_hash_is_rejected() -> None:
    assert not verify_password("secret", "broken")
