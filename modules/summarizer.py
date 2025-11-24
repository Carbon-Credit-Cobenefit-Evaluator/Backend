# modules/summarizer.py

from typing import Dict, List
from langchain.chat_models import init_chat_model
from langchain_core.messages import SystemMessage, HumanMessage
from config.settings import GROQ_MODEL_NAME

def summarize_factors(matches: Dict[str, List[str]]) -> List[Dict]:
    """
    matches: { factor_name: [sentence1, sentence2, ...] }
    returns: [ { "factor": ..., "summary": ... }, ... ]
    """
    llm = init_chat_model(GROQ_MODEL_NAME, model_provider="groq")
    summaries = []

    for factor, sents in matches.items():
        print(f"[INFO] Summarizing factor: {factor}")
        text = " ".join(sents)

        messages = [
            SystemMessage(content="You are an assistant that writes concise summaries of SDG-related evidence from carbon project documents."),
            HumanMessage(
                content=(
                    f"Factor: {factor}\n\n"
                    f"Evidence sentences:\n{text}\n\n"
                    "Task: Write a single concise paragraph (3–5 sentences) summarizing the co-benefit "
                    "evidence for this factor. Focus only on concrete actions and outcomes, not generic SDG theory."
                )
            ),
        ]

        out = llm.invoke(messages)
        summary_text = getattr(out, "content", str(out)).strip()

        summaries.append({
            "factor": factor,
            "summary": summary_text,
        })

    return summaries
