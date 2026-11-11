"""Instalador por usuário, configuração inicial e desinstalação pelo Windows."""
import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
from pathlib import Path

from sti.agente.instalacao import default_install_root, install_agent, remove_installation, validate_config
from sti.comum.releases import atomic_json, verify_file


def resources():
    base = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parent)) / 'resources'
    info = json.loads((base / 'setup-info.json').read_text(encoding='utf-8'))
    agent = base / 'STI_Agente.exe'
    verify_file(agent, info['agent'])
    return agent, info


def graphical_install(root):
    import tkinter as tk
    from tkinter import filedialog, messagebox, ttk

    payload, info = resources()
    window = tk.Tk()
    window.title('STI Agente — Instalação ' + info['version'])
    window.geometry('580x510')
    window.resizable(False, False)
    frame = ttk.Frame(window, padding=25)
    frame.pack(fill='both', expand=True)
    ttk.Label(frame, text='STI Agente', font=('Segoe UI', 22, 'bold')).pack(anchor='w')
    ttk.Label(frame, text='Instalação para o usuário atual • versão ' + info['version']).pack(anchor='w', pady=(4, 18))
    existing = root / 'sti-config.json'
    values = json.loads(existing.read_text(encoding='utf-8-sig')) if existing.exists() else {}
    host = tk.StringVar(value=values.get('STI_SERVER_IP', '10.2.116.121'))
    port = tk.StringVar(value=values.get('STI_SERVER_PORT', 5000))
    token = tk.StringVar(value=values.get('STI_AGENT_TOKEN', ''))
    https = tk.BooleanVar(value=values.get('STI_USE_HTTPS', False))
    startup = tk.BooleanVar(value=True)
    for label, variable, secret in (('IP ou DNS do servidor', host, False), ('Porta', port, False), ('Token do agente', token, True)):
        ttk.Label(frame, text=label).pack(anchor='w')
        ttk.Entry(frame, textvariable=variable, show='•' if secret else '').pack(fill='x', pady=(3, 10))
    ttk.Checkbutton(frame, text='Usar HTTPS', variable=https).pack(anchor='w')
    ttk.Checkbutton(frame, text='Iniciar o agente ao entrar no Windows', variable=startup).pack(anchor='w', pady=5)
    imported = dict(values)
    status = tk.StringVar(value='Configuração e identidade são preservadas nas atualizações.')
    busy = False

    def import_config():
        path = filedialog.askopenfilename(filetypes=[('Configuração JSON', '*.json')])
        if not path:
            return
        try:
            config = validate_config(json.loads(Path(path).read_text(encoding='utf-8-sig')))
            imported.clear()
            imported.update(config)
            host.set(config['STI_SERVER_IP'])
            port.set(config['STI_SERVER_PORT'])
            token.set(config['STI_AGENT_TOKEN'])
            https.set(config.get('STI_USE_HTTPS', False))
        except (OSError, ValueError) as error:
            messagebox.showerror('Configuração inválida', str(error))

    def finish(error=None):
        nonlocal busy
        busy = False
        install_button.config(state='normal')
        if error:
            status.set('Instalação não concluída.')
            messagebox.showerror('Instalação', error)
        else:
            status.set('Agente instalado e iniciado. Confira a comunicação no painel STI.')
            messagebox.showinfo('Instalação concluída', 'O agente foi instalado para este usuário e iniciado.')

    def install():
        nonlocal busy
        try:
            config = validate_config({**imported, 'STI_SERVER_IP': host.get(), 'STI_SERVER_PORT': port.get(),
                                      'STI_AGENT_TOKEN': token.get(), 'STI_USE_HTTPS': https.get()})
        except ValueError as error:
            messagebox.showerror('Configuração', str(error))
            return
        busy = True
        start_at_login = startup.get()
        install_button.config(state='disabled')
        status.set('Instalando e configurando o agente…')

        def worker():
            try:
                install_agent(payload, root, info['version'], config, startup=start_at_login, setup_source=sys.executable)
            except Exception as error:
                window.after(0, lambda text=str(error): finish(text))
            else:
                window.after(0, finish)
        threading.Thread(target=worker, name='STI-Installer').start()

    def close():
        if busy:
            messagebox.showinfo('Instalação', 'Aguarde a instalação terminar.')
        else:
            window.destroy()

    ttk.Button(frame, text='Importar agent-config.json', command=import_config).pack(fill='x', pady=(8, 6))
    install_button = ttk.Button(frame, text='Instalar / atualizar agente', command=install)
    install_button.pack(fill='x', pady=5)
    ttk.Label(frame, textvariable=status, wraplength=520).pack(anchor='w', pady=(12, 0))
    window.protocol('WM_DELETE_WINDOW', close)
    window.mainloop()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--target', type=Path, default=default_install_root())
    parser.add_argument('--config', type=Path)
    parser.add_argument('--silent', action='store_true')
    parser.add_argument('--no-startup', action='store_true')
    parser.add_argument('--no-launch', action='store_true')
    parser.add_argument('--uninstall', action='store_true')
    parser.add_argument('--remove-installed', action='store_true')
    parser.add_argument('--inspect', type=Path)
    args = parser.parse_args()
    try:
        if args.inspect:
            _, info = resources()
            atomic_json(args.inspect, info)
        elif args.remove_installed:
            remove_installation(args.target)
        elif args.uninstall:
            from tkinter import messagebox
            if not messagebox.askyesno('Desinstalar STI Agente', 'Remover o programa e a inicialização automática deste usuário? A configuração e a identidade serão mantidas.'):
                return
            helper = Path(tempfile.mkdtemp(prefix='sti-uninstall-')) / 'STI_Uninstall.exe'
            shutil.copyfile(sys.executable, helper)
            subprocess.Popen([str(helper), '--remove-installed', '--target', str(args.target)],
                             creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        elif args.silent:
            if not args.config:
                raise ValueError('Informe --config com o arquivo de configuração do agente.')
            payload, info = resources()
            config = validate_config(json.loads(args.config.read_text(encoding='utf-8-sig')))
            install_agent(payload, args.target, info['version'], config, startup=not args.no_startup,
                          launch=not args.no_launch, setup_source=sys.executable)
        else:
            graphical_install(args.target)
    except Exception as error:
        if args.silent or args.inspect or args.remove_installed:
            raise
        from tkinter import messagebox
        messagebox.showerror('STI Agente', str(error))
        raise SystemExit(1)


if __name__ == '__main__':
    main()
