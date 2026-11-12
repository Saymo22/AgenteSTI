"""Autor do MSI por usuário. Requer Windows e Python 3.12 (msilib)."""
import uuid
from pathlib import Path

from sti.comum.msi import UPGRADE_CODE, REGISTRY_KEY, product_code, msi_version

RUN_VALUE = 'AgenteSTI'


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
    summary.SetProperty(15, 10)  # compressed, per-user, no elevation
    summary.Persist()
    msilib.add_tables(db, sequence)
    add = lambda table, rows: msilib.add_data(db, table, rows)
    add('Property', [('UpgradeCode', UPGRADE_CODE), ('STI_STARTAGENT', '1'),
                     ('ARPNOMODIFY', '1'), ('ARPURLINFOABOUT', 'https://github.com/Saymo22/AgenteSTI'),
                     ('REINSTALLMODE', 'amus')])
    add('Directory', [('TARGETDIR', None, 'SourceDir'), ('LocalAppDataFolder', 'TARGETDIR', '.'),
                      ('STIDIR', 'LocalAppDataFolder', 'STI'), ('INSTALLDIR', 'STIDIR', 'Agent')])
    guid = lambda name: '{' + str(uuid.uuid5(uuid.UUID(UPGRADE_CODE), name)).upper() + '}'
    add('Component', [('AgentComponent', guid('agent'), 'INSTALLDIR', 256, None, 'AgentExe'),
                      ('MarkerComponent', guid('marker'), 'INSTALLDIR', 260, None, 'InstallDirRegistry'),
                      ('StartupComponent', guid('startup'), 'INSTALLDIR', 324, 'STI_STARTUP="1"', 'StartupRegistry')])
    add('Feature', [('AgentFeature', None, 'STI Agente', 'Inventário de equipamentos STI', 1, 1, 'INSTALLDIR', 0)])
    add('FeatureComponents', [('AgentFeature', component) for component in ('AgentComponent', 'MarkerComponent', 'StartupComponent')])
    cab = msilib.CAB('AgentCab')
    index, identifier = cab.append(str(agent), 'STI_Agente.exe', 'AgentExe')
    add('File', [(identifier, 'AgentComponent', 'AGENTE.EXE|STI_Agente.exe', agent.stat().st_size, version + '.0', None, 512, index)])
    add('Registry', [('InstallDirRegistry', 1, REGISTRY_KEY, 'InstallDir', '[INSTALLDIR]', 'MarkerComponent'),
                     ('ProductRegistry', 1, REGISTRY_KEY, 'ProductCode', '[ProductCode]', 'MarkerComponent'),
                     ('VersionRegistry', 1, REGISTRY_KEY, 'Version', '[ProductVersion]', 'MarkerComponent'),
                     ('PreferenceRegistry', 1, REGISTRY_KEY, 'Startup', '[STI_STARTUP]', 'MarkerComponent'),
                     ('StartupRegistry', 1, r'Software\Microsoft\Windows\CurrentVersion\Run', RUN_VALUE,
                      '"[INSTALLDIR]STI_Agente.exe"', 'StartupComponent')])
    # Clear the previous custom startup value before writing the MSI-managed preference.
    add('RemoveRegistry', [('LegacyStartup', 1, r'Software\Microsoft\Windows\CurrentVersion\Run', RUN_VALUE, 'MarkerComponent')])
    add('RemoveFile', [(f'LegacyFile{index}', 'MarkerComponent', name, 'INSTALLDIR', 1)
                       for index, name in enumerate(('STI_Agente_Setup.exe', 'previous-agent.exe', 'incoming-agent.exe', 'installation.json'))])
    add('RegLocator', [('StartupSearch', 1, REGISTRY_KEY, 'Startup', 2 | 16),
                       ('DirectorySearch', 1, REGISTRY_KEY, 'InstallDir', 2 | 16)])
    add('AppSearch', [('STI_PREVIOUS_STARTUP', 'StartupSearch'), ('INSTALLDIR', 'DirectorySearch')])
    add('Upgrade', [(UPGRADE_CODE, None, version, None, 1, None, 'STI_OLDPRODUCTS'),
                    (UPGRADE_CODE, version, None, None, 2, None, 'STI_NEWERPRODUCTS')])
    add('LaunchCondition', [('VersionNT64', 'O STI Agente requer Windows de 64 bits.'),
                            ('NOT STI_NEWERPRODUCTS', 'Uma versão mais recente já está instalada.')])
    add('CustomAction', [('PreviousStartup', 51, 'STI_STARTUP', '[STI_PREVIOUS_STARTUP]'),
                         ('DefaultStartup', 51, 'STI_STARTUP', '1'),
                         ('ConfigureAgent', 1042, 'AgentExe', '--msi-configure "[INSTALLDIR]." "[STI_CONFIGFILE]" "[OriginalDatabase]"'),
                         ('LaunchAgent', 18, 'AgentExe', '--msi-launch "[STI_PREVIOUS_PID]" "[ReplacedFilesInUse]"')])
    # Validate and install the new payload before removing the old product.
    # Stable component GUIDs preserve shared files during the late major upgrade.
    view = db.OpenView("UPDATE `InstallExecuteSequence` SET `Sequence`=6550 WHERE `Action`='RemoveExistingProducts'")
    view.Execute(None)
    view = db.OpenView("UPDATE `InstallExecuteSequence` SET `Sequence`=1390 WHERE `Action`='LaunchConditions'")
    view.Execute(None)
    add('InstallExecuteSequence', [('PreviousStartup', 'NOT STI_STARTUP AND STI_PREVIOUS_STARTUP', 410),
                                  ('DefaultStartup', 'NOT STI_STARTUP', 420),
                                  ('ConfigureAgent', 'NOT REMOVE~="ALL"', 4100),
                                  ('InstallExecute', None, 6500),
                                  ('LaunchAgent', 'NOT REMOVE~="ALL" AND STI_STARTAGENT="1"', 6701)])
    add('InstallUISequence', [('PreviousStartup', 'NOT STI_STARTUP AND STI_PREVIOUS_STARTUP', 410),
                             ('DefaultStartup', 'NOT STI_STARTUP', 420), ('ConfigurationDialog', 'NOT REMOVE~="ALL"', 1290)])
    dialog = msilib.Dialog(db, 'ConfigurationDialog', 50, 50, 380, 210, 3, 'STI Agente [ProductVersion]', 'ConfigPath', 'Install', 'Cancel')
    dialog.text('Title', 20, 12, 340, 20, 3, 'Instalar ou atualizar o STI Agente')
    dialog.text('Help', 20, 40, 340, 38, 3, 'Na primeira instalação, deixe agent-config.json ao lado do MSI ou informe seu caminho abaixo. A configuração existente será preservada.')
    dialog.control('ConfigPath', 'Edit', 20, 84, 340, 20, 3, 'STI_CONFIGFILE', None, 'Startup', None)
    dialog.radiogroup('Startup', 20, 114, 340, 38, 3, 'STI_STARTUP', None, 'Install')
    add('RadioButton', [('STI_STARTUP', 1, '1', 0, 0, 330, 16, 'Iniciar automaticamente ao entrar no Windows', None),
                        ('STI_STARTUP', 2, '0', 0, 19, 330, 16, 'Iniciar manualmente', None)])
    dialog.pushbutton('Install', 200, 166, 78, 22, 3, 'Instalar', 'Cancel').event('EndDialog', 'Return')
    dialog.pushbutton('Cancel', 284, 166, 78, 22, 3, 'Cancelar', 'ConfigPath').event('EndDialog', 'Exit')
    cab.commit(db)
    db.Commit()
    return destination
