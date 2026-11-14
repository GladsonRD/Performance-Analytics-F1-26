' Instalador da Telemetria F1 26: roda o instalar.ps1 sem abrir janela de comando.
Set fso = CreateObject("Scripting.FileSystemObject")
pasta = fso.GetParentFolderName(WScript.ScriptFullName)
CreateObject("WScript.Shell").Run "powershell.exe -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File """ & pasta & "\instalar.ps1""", 0, False
