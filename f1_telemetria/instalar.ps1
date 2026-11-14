# Instalador da Telemetria F1 26 (roda escondido; só mostra janelas de aviso).
$ErrorActionPreference = 'Continue'
$pasta = Split-Path -Parent $MyInvocation.MyCommand.Path
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
[System.Windows.Forms.Application]::EnableVisualStyles()
$TITULO = 'Performance Analytics F1 26'

function Aviso($texto, $icone = 'Information') {
    [System.Windows.Forms.MessageBox]::Show($texto, $TITULO, 'OK', $icone) | Out-Null
}

function Achar-Python {
    foreach ($cmd in @('py', 'python')) {
        try {
            $v = & $cmd -c "import sys; print(sys.version_info >= (3, 8))" 2>$null
            if ($LASTEXITCODE -eq 0 -and "$v".Trim() -eq 'True') { return $cmd }
        } catch { }
    }
    return $null
}

$py = Achar-Python
if (-not $py) {
    $r = [System.Windows.Forms.MessageBox]::Show(
        "O Python não está instalado neste computador e é necessário para a telemetria.`n`nPosso instalar agora? Leva alguns minutos.",
        $TITULO, 'YesNo', 'Question')
    if ($r -ne 'Yes') { exit 1 }

    if (Get-Command winget -ErrorAction SilentlyContinue) {
        # janelinha de "aguarde" enquanto o winget trabalha escondido
        $form = New-Object System.Windows.Forms.Form
        $form.Text = $TITULO
        $form.Size = New-Object System.Drawing.Size(380, 130)
        $form.StartPosition = 'CenterScreen'
        $form.FormBorderStyle = 'FixedDialog'
        $form.ControlBox = $false
        $form.TopMost = $true
        try { $form.Icon = New-Object System.Drawing.Icon (Join-Path $pasta 'icone.ico') } catch { }
        $lbl = New-Object System.Windows.Forms.Label
        $lbl.Text = 'Instalando o Python, aguarde...'
        $lbl.AutoSize = $true
        $lbl.Location = New-Object System.Drawing.Point(20, 18)
        $form.Controls.Add($lbl)
        $barra = New-Object System.Windows.Forms.ProgressBar
        $barra.Style = 'Marquee'
        $barra.Location = New-Object System.Drawing.Point(20, 48)
        $barra.Size = New-Object System.Drawing.Size(325, 18)
        $form.Controls.Add($barra)
        $form.Show()
        $proc = Start-Process winget -WindowStyle Hidden -PassThru -ArgumentList @(
            'install', '--id', 'Python.Python.3.12', '-e', '--scope', 'user', '--silent',
            '--accept-package-agreements', '--accept-source-agreements')
        while (-not $proc.HasExited) {
            [System.Windows.Forms.Application]::DoEvents()
            Start-Sleep -Milliseconds 100
        }
        $form.Close()
        $env:Path = [Environment]::GetEnvironmentVariable('Path', 'Machine') + ';' + [Environment]::GetEnvironmentVariable('Path', 'User')
        $py = Achar-Python
    }
    if (-not $py) {
        Aviso ("Não consegui instalar o Python sozinho.`n`nVou abrir a página de download. Instale e MARQUE a opção " +
               "`"Add Python to PATH`". Depois abra o INSTALAR de novo.") 'Warning'
        Start-Process 'https://www.python.org/downloads/'
        exit 1
    }
}

& $py -c "import tkinter" 2>$null
if ($LASTEXITCODE -ne 0) {
    Aviso 'O Python deste computador veio sem a parte de janelas (tkinter). Reinstale o Python do python.org com as opções padrão e abra o INSTALAR de novo.' 'Error'
    exit 1
}
$pyw = "$(& $py -c "import sys, os; print(os.path.join(os.path.dirname(sys.executable), 'pythonw.exe'))")".Trim()
if (-not (Test-Path $pyw)) { $pyw = $null }

# atalho na Área de Trabalho
$desktop = [Environment]::GetFolderPath('Desktop')
$shell = New-Object -ComObject WScript.Shell
$antigo = Join-Path $desktop 'Telemetria F1 26.lnk'
if (Test-Path $antigo) { Remove-Item $antigo -Force }
$a = $shell.CreateShortcut((Join-Path $desktop 'Performance Analytics F1 26.lnk'))
if ($pyw) {
    $a.TargetPath = $pyw
    $a.Arguments = '"' + (Join-Path $pasta 'painel.pyw') + '"'
} else {
    $a.TargetPath = Join-Path $pasta 'modo_texto.bat'
}
$a.WorkingDirectory = $pasta
$a.IconLocation = (Join-Path $pasta 'icone.ico') + ',0'
$a.Description = 'Grava a telemetria do F1 26 e gera o relatório ao fim da sessão'
$a.Save()

Aviso ("Pronto! O atalho `"Performance Analytics F1 26`" está na sua Área de Trabalho.`n`n" +
       "No jogo, em Configurações > Telemetria, ligue o UDP: IP 127.0.0.1, porta 20777, formato 2026.`n`n" +
       "Se o Windows perguntar sobre o firewall, clique em Permitir.`n`nClique em OK para abrir a telemetria.")
if ($pyw) {
    Start-Process -FilePath $pyw -ArgumentList ('"' + (Join-Path $pasta 'painel.pyw') + '"') -WorkingDirectory $pasta
}
