"""Entrada do agente Windows; implementação em sti.agente."""
import sys

if __name__ == '__main__' and len(sys.argv) > 1 and sys.argv[1].startswith('--msi-'):
    from sti.agente.msi import entry
    raise SystemExit(entry(sys.argv[1:]))

from sti.agente.cliente import main

if __name__ == "__main__":
    main()
