"""MSI x64 por máquina; serviço instalado e controlado pelas tabelas nativas."""
import uuid
from pathlib import Path

from sti.comum.msi import SERVICE_UPGRADE_CODE, REGISTRY_KEY, product_code, msi_version
from sti.comum.servico import SERVICE_NAME, SERVICE_DISPLAY_NAME


def build_msi(agent, destination, version):
    import msilib
    from msilib import schema, sequence

    version = msi_version(version)
    agent, destination = Path(agent).resolve(), Path(destination).resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        destination.unlink()
    db = msilib.init_database(str(destination), schema, 'STI Agente', product_code(version), version, 'STI')
    summary = db.GetSummaryInformation(20)
    summary.SetProperty(7, 'x64;1033')
    summary.SetProperty(15, 2)  # compressed; instalação elevada por máquina
    summary.Persist()
    msilib.add_tables(db, sequence)
    add = lambda table, rows: msilib.add_data(db, table, rows)
    add('Property', [('UpgradeCode', SERVICE_UPGRADE_CODE), ('ALLUSERS', '1'), ('STI_INSTALL_MODE', 'service'),
        ('ARPNOMODIFY', '1'), ('ARPURLINFOABOUT', 'https://github.com/Saymo22/AgenteSTI'),
        ('SecureCustomProperties', 'STI_CONFIGFILE;STI_LEGACYDIR;STI_USERSID;STI_OLDPRODUCTS;STI_NEWERPRODUCTS'),
        ('REINSTALLMODE', 'amus'), ('MsiLogging', 'voicewarmup')])
    add('Directory', [('TARGETDIR', None, 'SourceDir'), ('ProgramFiles64Folder', 'TARGETDIR', '.'),
        ('STIVENDOR', 'ProgramFiles64Folder', 'STI'), ('INSTALLDIR', 'STIVENDOR', 'AgentService')])
    guid = lambda name: '{' + str(uuid.uuid5(uuid.UUID(SERVICE_UPGRADE_CODE), name)).upper() + '}'
    add('Component', [('AgentComponent', guid('agent'), 'INSTALLDIR', 256, None, 'AgentExe'),
        ('MarkerComponent', guid('marker'), 'INSTALLDIR', 260, None, 'InstallDirRegistry')])
    add('Feature', [('AgentFeature', None, 'STI Agente', 'Serviço de inventário e monitoramento STI', 1, 1, 'INSTALLDIR', 0)])
    add('FeatureComponents', [('AgentFeature', name) for name in ('AgentComponent', 'MarkerComponent')])
    cab = msilib.CAB('AgentCab')
    index, identifier = cab.append(str(agent), 'STI_Agente.exe', 'AgentExe')
    add('File', [(identifier, 'AgentComponent', 'AGENTE.EXE|STI_Agente.exe', agent.stat().st_size, version+'.0', None, 512, index)])
    add('Registry', [('InstallDirRegistry', 2, REGISTRY_KEY, 'InstallDir', '[INSTALLDIR]', 'MarkerComponent'),
        ('ProductRegistry', 2, REGISTRY_KEY, 'ProductCode', '[ProductCode]', 'MarkerComponent'),
        ('VersionRegistry', 2, REGISTRY_KEY, 'Version', '[ProductVersion]', 'MarkerComponent'),
        ('ModeRegistry', 2, REGISTRY_KEY, 'Mode', 'service', 'MarkerComponent'),
        ('PreferenceRegistry', 2, REGISTRY_KEY, 'Startup', '1', 'MarkerComponent')])
    add('RegLocator', [('MachineDirectory', 2, REGISTRY_KEY, 'InstallDir', 2 | 16),
                       ('LegacyDirectory', 1, REGISTRY_KEY, 'InstallDir', 2 | 16)])
    add('AppSearch', [('INSTALLDIR', 'MachineDirectory'), ('STI_LEGACYDIR', 'LegacyDirectory')])
    # Escopo separado: um MSI por usuário não é removido dentro da transação SYSTEM.
    add('Upgrade', [(SERVICE_UPGRADE_CODE, None, version, None, 1, None, 'STI_OLDPRODUCTS'),
                   (SERVICE_UPGRADE_CODE, version, None, None, 2, None, 'STI_NEWERPRODUCTS')])
    add('LaunchCondition', [('VersionNT64', 'O STI Agente requer Windows de 64 bits.'),
                           ('NOT STI_NEWERPRODUCTS', 'Uma versão mais recente já está instalada.')])
    add('ServiceInstall', [('AgentService', SERVICE_NAME, SERVICE_DISPLAY_NAME, 16, 2, 32769,
        None, None, None, None, '--service', 'AgentComponent',
        'Inventário e monitoramento STI, inclusive sem usuário conectado.')])
    add('ServiceControl', [('AgentServiceControl', SERVICE_NAME, 163, None, 1, 'AgentComponent')])
    add('CustomAction', [('CaptureUserSid', 51, 'STI_USERSID', '[UserSID]'),
        # A barra final do InstallDir antigo escapava a aspa no parser do Windows.
        # O sufixo \\. mantém diretórios com ou sem barra final como um único argumento.
        ('ConfigureService', 3090, 'AgentExe', '--msi-service-configure "[INSTALLDIR]." "[STI_CONFIGFILE]" "[OriginalDatabase]" "[STI_LEGACYDIR]\\." "[STI_USERSID]"'),
        ('ConfigureRecovery', 3090, 'AgentExe', '--msi-service-recovery'),
        ('CommitMigration', 2578, 'AgentExe', '--msi-service-migrate "[STI_LEGACYDIR]\\." "[STI_USERSID]"')])
    for action, number in [('RemoveExistingProducts', 1550), ('LaunchConditions', 1390)]:
        view = db.OpenView(f"UPDATE `InstallExecuteSequence` SET `Sequence`={number} WHERE `Action`='{action}'")
        view.Execute(None)
        view.Close()
    add('InstallExecuteSequence', [('CaptureUserSid', 'NOT STI_USERSID', 430),
        ('ConfigureService', 'NOT REMOVE~="ALL"', 4100),
        ('ConfigureRecovery', 'NOT REMOVE~="ALL"', 5850),
        ('CommitMigration', 'NOT REMOVE~="ALL" AND STI_LEGACYDIR', 6100)])
    add('InstallUISequence', [('CaptureUserSid', 'NOT STI_USERSID', 430),
        ('ConfigurationDialog', 'NOT REMOVE~="ALL"', 1290)])
    dialog = msilib.Dialog(db, 'ConfigurationDialog', 50, 50, 400, 250, 3,
        'STI Agente [ProductVersion]', 'ConfigPath', 'Install', 'Cancel')
    dialog.text('Title', 20, 12, 360, 20, 3, 'Instalar o serviço de monitoramento STI')
    dialog.text('Help', 20, 40, 360, 48, 3,
        'Funciona antes do login e após sair do Windows. Requer autorização de administrador. Informe agent-config.json ou deixe o arquivo ao lado do MSI.')
    dialog.control('ConfigPath', 'Edit', 20, 92, 360, 20, 3, 'STI_CONFIGFILE', None, 'LegacyPath', None)
    dialog.text('LegacyHelp', 20, 122, 360, 30, 3,
        'Migrar instalação anterior: confirme a pasta do agente do usuário. Deixe vazio para instalação nova.')
    dialog.control('LegacyPath', 'Edit', 20, 156, 360, 20, 3, 'STI_LEGACYDIR', None, 'Install', None)
    dialog.pushbutton('Install', 210, 200, 78, 24, 3, 'Instalar', 'Cancel').event('EndDialog', 'Return')
    dialog.pushbutton('Cancel', 298, 200, 78, 24, 3, 'Cancelar', 'ConfigPath').event('EndDialog', 'Exit')
    cab.commit(db)
    db.Commit()
    return destination
