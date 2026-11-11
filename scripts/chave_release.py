"""Cria uma chave de publicação local e a chave pública distribuída aos agentes."""
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey


def generate(private_path, public_path):
    private_path, public_path = Path(private_path), Path(public_path)
    if private_path.exists() or public_path.exists():
        raise ValueError('A chave já existe. Preserve-a para assinar as próximas releases.')
    private_path.parent.mkdir(parents=True, exist_ok=True)
    key = Ed25519PrivateKey.generate()
    with private_path.open('xb') as stream:
        stream.write(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                      serialization.NoEncryption()))
    with public_path.open('xb') as stream:
        stream.write(key.public_key().public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo))


if __name__ == '__main__':
    root = Path(__file__).resolve().parents[1]
    generate(root / '.release-keys/agent-signing-key.pem', root / 'sti/comum/release-public-key.pem')
    print('Chave privada criada em .release-keys. A chave pública será incluída nos agentes.')
