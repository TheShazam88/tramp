from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from app.config import KeyUnlockMode, MasterKeySource, get_settings
from app.security.crypto import decrypt_with_app_secret, derive_aes_key, encrypt_with_app_secret


@dataclass(slots=True)
class KeyMaterial:
    ciphertext_key_id: str
    plaintext: bytearray

    def zeroize(self) -> None:
        for index in range(len(self.plaintext)):
            self.plaintext[index] = 0


class KeyProvider(Protocol):
    def get_key(self, *, passphrase: str | None = None) -> KeyMaterial:
        ...


class MasterKeyProvider:
    def get_key(self, *, passphrase: str | None = None) -> KeyMaterial:
        if not passphrase:
            raise RuntimeError("A master key passphrase is required in master-key mode.")

        key = derive_aes_key(material=passphrase, salt=b"travel-watch-master-key")
        return KeyMaterial(ciphertext_key_id="master-key", plaintext=bytearray(key))


class AutoUnlockKeyProvider:
    def get_key(self, *, passphrase: str | None = None) -> KeyMaterial:
        del passphrase
        settings = get_settings()
        if settings.master_key_source == MasterKeySource.LOCAL_FILE:
            path = Path(settings.auto_unlock_local_file_path or ".tramp-auto-unlock.key")
            if not path.exists():
                if not settings.auto_unlock_seed_material:
                    raise RuntimeError(
                        "AUTO_UNLOCK_SEED_MATERIAL is required to bootstrap local-file auto-unlock."
                    )
                encrypted = encrypt_with_app_secret(
                    plaintext=settings.auto_unlock_seed_material.get_secret_value(),
                    aad="auto-unlock-local-file",
                )
                path.write_text(encrypted, encoding="utf-8")
            encrypted_material = path.read_text(encoding="utf-8").strip()
            material = decrypt_with_app_secret(
                ciphertext=encrypted_material,
                aad="auto-unlock-local-file",
            )
            key = derive_aes_key(material=material, salt=b"travel-watch-auto-unlock")
            return KeyMaterial(ciphertext_key_id="auto-unlock-local-file", plaintext=bytearray(key))

        raise RuntimeError(
            "Auto-unlock is implemented for MASTER_KEY_SOURCE=local_file in localhost mode. "
            "Vault/keychain providers are not wired yet."
        )


def get_key_provider() -> KeyProvider:
    settings = get_settings()
    if settings.key_unlock_mode == KeyUnlockMode.AUTO:
        return AutoUnlockKeyProvider()
    return MasterKeyProvider()
