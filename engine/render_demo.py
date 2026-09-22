"""Reproducible silent sample used by the web demo; never calls paid APIs."""
from pathlib import Path

from app.config import Settings
from app.services.video import render
from app.services.voice import synthesize

TEXT = (
    "Dein nächster Content steckt schon in deinem letzten Video. "
    "Du brauchst nicht jeden Tag eine neue Idee. Nimm ein Video, in dem du ein Problem wirklich löst. "
    "Finde drei Aussagen, die für sich allein verständlich sind. Aus jeder machst du einen kurzen Clip: "
    "ein klarer Einstieg, ein konkretes Beispiel und eine hilfreiche Erkenntnis. "
    "AI kann dir beim Transkribieren und beim ersten Skript helfen. Aber du prüfst, ob der Kontext stimmt. "
    "So wird aus einer guten Aufnahme eine kleine Content-Serie. Deine Expertise bleibt. Das Format verändert sich. "
    "Speichere dir den Workflow für dein nächstes Video."
)

if __name__ == "__main__":
    import shutil
    import tempfile

    settings = Settings(openai_api_key=None, elevenlabs_api_key=None, elevenlabs_voice_id=None,
                        allow_demo_fallback=True, _env_file=None)
    with tempfile.TemporaryDirectory(prefix="studio-demo-") as directory:
        folder = Path(directory)
        audio = synthesize(TEXT, folder, settings)
        video = render(TEXT, audio, folder, settings)
        destination = Path(__file__).resolve().parent.parent / "public" / "demo-short.mp4"
        shutil.copy2(video, destination)
        print(destination)
