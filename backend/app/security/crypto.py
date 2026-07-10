from __future__ import annotations

import base64
import os
from dataclasses import dataclass

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

from app.config import get_settings

PBKDF2_ITERATIONS = 390_000
NONCE_SIZE = 12
SALT_SIZE = 16


@dataclass(slots=True)
class EncryptedPayload:
    salt: bytes
    nonce: bytes
    ciphertext: bytes

    def serialize(self) -> str:
        return base64.urlsafe_b64encode(self.salt + self.nonce + self.ciphertext).decode("utf-8")

    @classmethod
    def parse(cls, value: str) -> "EncryptedPayload":
        raw = base64.urlsafe_b64decode(value.encode("utf-8"))
        salt = raw[:SALT_SIZE]
        nonce = raw[SALT_SIZE : SALT_SIZE + NONCE_SIZE]
        ciphertext = raw[SALT_SIZE + NONCE_SIZE :]
        return cls(salt=salt, nonce=nonce, ciphertext=ciphertext)


def derive_aes_key(*, material: str, salt: bytes) -> bytes:
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=PBKDF2_ITERATIONS,
    )
    return kdf.derive(material.encode("utf-8"))


def encrypt_with_material(*, plaintext: str, material: str, aad: str | None = None) -> str:
    salt = os.urandom(SALT_SIZE)
    nonce = os.urandom(NONCE_SIZE)
    key = derive_aes_key(material=material, salt=salt)
    ciphertext = AESGCM(key).encrypt(
        nonce,
        plaintext.encode("utf-8"),
        aad.encode("utf-8") if aad else None,
    )
    return EncryptedPayload(salt=salt, nonce=nonce, ciphertext=ciphertext).serialize()


def decrypt_with_material(*, ciphertext: str, material: str, aad: str | None = None) -> str:
    payload = EncryptedPayload.parse(ciphertext)
    key = derive_aes_key(material=material, salt=payload.salt)
    plaintext = AESGCM(key).decrypt(
        payload.nonce,
        payload.ciphertext,
        aad.encode("utf-8") if aad else None,
    )
    return plaintext.decode("utf-8")


def encrypt_with_app_secret(*, plaintext: str, aad: str | None = None) -> str:
    settings = get_settings()
    key_material = settings.app_secret.get_secret_value()
    return encrypt_with_material(plaintext=plaintext, material=key_material, aad=aad)


def decrypt_with_app_secret(*, ciphertext: str, aad: str | None = None) -> str:
    settings = get_settings()
    key_material = settings.app_secret.get_secret_value()
    return decrypt_with_material(ciphertext=ciphertext, material=key_material, aad=aad)
