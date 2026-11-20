"""Identidade do produto Windows Installer (estável entre versões)."""
import uuid

UPGRADE_CODE = '{76419164-14FA-4CA3-9165-95B38A3B36AB}'
SERVICE_UPGRADE_CODE = '{08174D84-2847-46E3-A186-0E42F2CDFB55}'
REGISTRY_KEY = r'Software\STI\Agent'


def machine_package(version):
    from sti.comum.releases import version_tuple
    return version_tuple(version) >= (3, 5, 2)


def upgrade_code(version):
    return SERVICE_UPGRADE_CODE if machine_package(version) else UPGRADE_CODE


def product_code(version):
    return '{' + str(uuid.uuid5(uuid.UUID(UPGRADE_CODE), version)).upper() + '}'


def msi_version(version):
    from sti.comum.releases import version_tuple
    numbers = version_tuple(version)
    if numbers[0] > 255 or numbers[1] > 255 or numbers[2] > 65535:
        raise ValueError('MSI exige versão até 255.255.65535.')
    return version
