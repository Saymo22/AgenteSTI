"""Gera segredos locais e um arquivo de distribuição sem a senha administrativa."""
import json
import secrets
from pathlib import Path


def preparar(directory=None):
    directory = Path(directory) if directory else Path(__file__).resolve().parent
    server_file = directory / "sti-config.json"
    agent_file = directory / "agent-config.json"
    if server_file.exists() or agent_file.exists():
        raise SystemExit("Configuração já existe; não sobrescrita. Edite os arquivos locais existentes.")
    token = secrets.token_hex(32)
    server = {
        "STI_HOST": "0.0.0.0", "STI_PORT": 5000, "NETWORK": "10.2.116.0/22",
        "STI_AGENT_TOKEN": token, "STI_ADMIN_PASSWORD": secrets.token_urlsafe(24),
        "STI_SECRET_KEY": secrets.token_hex(32), "STI_HTTPS": False,
    }
    agent = {
        "STI_SERVER_IP": "10.2.116.121", "STI_SERVER_PORT": 5000,
        "STI_AGENT_TOKEN": token, "STI_USE_HTTPS": False,
        "STI_ALLOW_POWER_COMMANDS": False, "AGENT_INTERVAL": 30, "RETRY_INTERVAL": 10,
    }
    for path, contents in ((server_file, server), (agent_file, agent)):
        with path.open("x", encoding="utf-8") as stream:
            json.dump(contents, stream, indent=2, ensure_ascii=False)
            stream.write("\n")
    print("Configuração do servidor criada em sti-config.json (contém a senha de login).")
    print("Configuração dos agentes criada em agent-config.json (não contém a senha administrativa).")
    print("Confira o IP do servidor antes de distribuir. Não publique esses arquivos.")


if __name__ == "__main__":
    preparar()
