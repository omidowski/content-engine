import json

from openai import OpenAI

from app.config import Settings
from app.schemas import ContentCreate, GeneratedContent


SYSTEM_PROMPT = """You create factual 30-60 second vertical-video scripts.
Return only JSON matching the requested schema. Never invent citations.
Use only supplied sources for source-specific claims. If no sources are supplied,
write evergreen educational content and mark the source list empty. Keep the hook
specific, the script natural for spoken delivery, and avoid exaggerated promises."""


def _demo_content(request: ContentCreate) -> GeneratedContent:
    if request.language == "de":
        return GeneratedContent(
            hook=f"Was verändert {request.topic} wirklich im Arbeitsalltag?",
            script=(
                f"{request.topic} klingt zunächst abstrakt. Entscheidend ist aber der konkrete Prozess: "
                "Eine klar definierte Aufgabe wird erfasst, mit den passenden Informationen verarbeitet und "
                "anschließend von einem Menschen geprüft. Starte mit einem kleinen, messbaren Workflow, statt "
                "sofort alles zu automatisieren. Miss Zeitersparnis, Qualität und Fehlerquote. So erkennst du, "
                "ob die Lösung echten Nutzen liefert und sicher skaliert werden kann."
            ),
            title=f"{request.topic}: praktisch erklärt",
            caption=f"Ein kompakter Blick auf {request.topic}. Ergebnisse vor dem Skalieren messen und prüfen.",
            cta="Folge für weitere praktische AI-Automationen.",
            sources=[s.model_dump(mode="json") for s in request.sources],
        )
    return GeneratedContent(
        hook=f"What does {request.topic} actually change at work?",
        script=(
            f"{request.topic} may sound abstract, but the practical workflow matters. A clearly defined task "
            "is captured, processed with the right information, and reviewed by a person. Start with one small, "
            "measurable workflow instead of automating everything. Track time saved, quality, and error rates. "
            "That shows whether the solution creates real value and can be scaled safely."
        ),
        title=f"{request.topic}: a practical explanation",
        caption=f"A compact look at {request.topic}. Measure and review before scaling.",
        cta="Follow for more practical AI automations.",
        sources=[s.model_dump(mode="json") for s in request.sources],
    )


def generate_content(request: ContentCreate, settings: Settings) -> GeneratedContent:
    if not settings.openai_api_key:
        if settings.allow_demo_fallback:
            return _demo_content(request)
        raise RuntimeError("OPENAI_API_KEY is required")

    client = OpenAI(api_key=settings.openai_api_key)
    source_payload = [s.model_dump(mode="json") for s in request.sources]
    response = client.responses.parse(
        model=settings.openai_model,
        input=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": json.dumps(
                    {"topic": request.topic, "language": request.language, "sources": source_payload},
                    ensure_ascii=False,
                ),
            },
        ],
        text_format=GeneratedContent,
    )
    if response.output_parsed is None:
        raise RuntimeError("The model did not return structured content")
    result = response.output_parsed
    result.sources = source_payload
    return result

