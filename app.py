"""Entrada do servidor para o PyCharm e WSGI; implementação em sti.servidor."""
from sti.servidor.app import app, create_app, main

if __name__ == "__main__":
    main()
