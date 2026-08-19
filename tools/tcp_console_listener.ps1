param(
    [int]$Port = 5000,
    [string]$BindAddress = "0.0.0.0",
    [string]$OutputPath = ""
)

$ErrorActionPreference = "Stop"

if (-not $OutputPath) {
    $timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
    $OutputPath = Join-Path (Join-Path $PSScriptRoot "..\\logs") "tcp_console_$timestamp.log"
}

$outputDirectory = Split-Path -Parent $OutputPath
New-Item -ItemType Directory -Force -Path $outputDirectory | Out-Null

$listener = [System.Net.Sockets.TcpListener]::new([System.Net.IPAddress]::Parse($BindAddress), $Port)
$listener.Start()

Add-Content -Path $OutputPath -Value ("[{0}] LISTEN {1}:{2}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss.fff"), $BindAddress, $Port)

try {
    while ($true) {
        $client = $listener.AcceptTcpClient()
        $remote = $client.Client.RemoteEndPoint.ToString()
        Add-Content -Path $OutputPath -Value ("[{0}] CONNECT {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss.fff"), $remote)

        try {
            $stream = $client.GetStream()
            $buffer = New-Object byte[] 4096

            while ($client.Connected) {
                $read = $stream.Read($buffer, 0, $buffer.Length)
                if ($read -le 0) {
                    break
                }

                $bytes = $buffer[0..($read - 1)]
                $hex = ($bytes | ForEach-Object { $_.ToString("X2") }) -join " "
                $text = [System.Text.Encoding]::UTF8.GetString($bytes).Trim()
                if (-not $text) {
                    $text = "<empty-after-trim>"
                }

                Add-Content -Path $OutputPath -Value ("[{0}] DATA {1} bytes={2} text={3} hex={4}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss.fff"), $remote, $read, $text, $hex)
            }
        }
        finally {
            Add-Content -Path $OutputPath -Value ("[{0}] DISCONNECT {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss.fff"), $remote)
            $client.Close()
        }
    }
}
finally {
    $listener.Stop()
    Add-Content -Path $OutputPath -Value ("[{0}] STOP" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss.fff"))
}
