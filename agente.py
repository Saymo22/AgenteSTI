"""Entrada do agente Windows; implementação em sti.agente."""
import sys

if __name__ == '__main__' and len(sys.argv) == 3 and sys.argv[1] == '--apply-update':
    from sti.agente.atualizacao import run_update_helper
    raise SystemExit(0 if run_update_helper(sys.argv[2]) else 1)

from sti.agente.cliente import main

if __name__ == "__main__":
    main()
