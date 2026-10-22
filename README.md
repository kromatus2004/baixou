# Baixou

**Colou o link, baixou o vídeo.** Gerenciador de downloads gratuito para Windows: baixa vídeos e músicas de mais de mil sites (YouTube, Instagram, TikTok, X, Vimeo…), na qualidade que você escolher.

**[⬇ Baixar o instalador](https://github.com/kromatus2004/baixou/releases/latest/download/Baixou-Setup.exe)** · [Site](https://kromatus2004.github.io/baixou/)

## Recursos

- Um clique: copie o link, clique em **Colar link** (ou aperte Ctrl+V na janela) e pronto
- Vídeo em MP4, MKV ou WEBM, do 360p ao 8K
- Só o áudio em MP3, M4A ou WAV
- Playlists inteiras, legendas (PT/EN) e vários downloads ao mesmo tempo
- Navegador embutido: entre nas suas contas dentro do Baixou e baixe vídeos privados com um clique
- Também aceita o login do navegador ou um arquivo `cookies.txt`
- Tudo roda no seu PC: nada passa por servidor de terceiros

## Para desenvolvedores

Precisa de Python 3.12, ffmpeg e Node.js no PATH.

```bash
pip install "yt-dlp[default]" pywebview
python server.py            # abre na janela própria
python server.py --browser  # abre no navegador
```

### Gerar o instalador

1. Coloque `ffmpeg.exe`, `ffprobe.exe` (com as DLLs) e `node.exe` em `build/bin/`
2. `pyinstaller` (veja o comando em `build.ps1`)
3. Compile `installer/baixou.iss` com o Inno Setup 6

## Aviso

Use com responsabilidade: baixe só conteúdo que você tem direito de guardar. O Baixou usa o [yt-dlp](https://github.com/yt-dlp/yt-dlp) e o [FFmpeg](https://ffmpeg.org); veja `build/licenses/TERCEIROS.txt` no instalador.
