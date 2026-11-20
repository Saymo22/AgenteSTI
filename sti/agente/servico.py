"""Hospedagem explícita pelo SCM. Instalação e remoção pertencem ao MSI."""
import threading

import servicemanager
import win32service
import win32serviceutil

from sti.comum.servico import SERVICE_NAME, SERVICE_DISPLAY_NAME, prepare_environment


class AgentService(win32serviceutil.ServiceFramework):
    _svc_name_ = SERVICE_NAME
    _svc_display_name_ = SERVICE_DISPLAY_NAME
    _svc_description_ = 'Inventário e monitoramento STI, inclusive sem usuário conectado.'

    def __init__(self, args):
        super().__init__(args)
        self.stop_event = threading.Event()

    def SvcStop(self):
        self.ReportServiceStatus(win32service.SERVICE_STOP_PENDING, waitHint=30000)
        self.stop_event.set()

    def SvcShutdown(self):
        self.SvcStop()

    def SvcDoRun(self):
        # O dispatcher e o controle de parada já estão disponíveis antes da coleta de hardware.
        prepare_environment()
        from sti.agente.cliente import iniciar_agente
        updating = iniciar_agente(self.stop_event)
        if not self.stop_event.is_set() and not updating:
            raise RuntimeError('O agente não iniciou. Consulte a configuração e os logs do serviço.')


def run():
    prepare_environment()
    servicemanager.Initialize()
    servicemanager.PrepareToHostSingle(AgentService)
    servicemanager.StartServiceCtrlDispatcher()


def send_message(message):
    import win32ts
    sessions = [item for item in win32ts.WTSEnumerateSessions(None, 1, 0)
                if item['State'] == win32ts.WTSActive and item['SessionId'] != 0]
    if not sessions:
        return 'rejected', 'Nenhum usuário conectado para receber a mensagem.'
    # Prioriza o console físico, depois uma sessão remota ativa.
    console = win32ts.WTSGetActiveConsoleSessionId()
    sessions.sort(key=lambda item: (item['SessionId'] != console, item['SessionId']))
    response = win32ts.WTSSendMessage(None, sessions[0]['SessionId'],
        'STI - Mensagem da Administração', str(message), 0x40, 30, True)
    return ('completed', 'Mensagem confirmada pelo usuário.') if response == 1 else (
        'failed', 'A sessão não confirmou a mensagem no prazo de 30 segundos.')
