"""spaCy base parse provider: tokenization, POS, NER, sentence boundaries."""

from __future__ import annotations

from typing import Any

from mapu.extraction.types import BaseParse, EntityMention


class SpacyBaseParser:
    """Wraps a spaCy Language pipeline to produce BaseParse for extraction."""

    def __init__(self, nlp: Any) -> None:
        self._nlp = nlp

    def parse(self, text: str) -> BaseParse:
        doc = self._nlp(text)

        tokens = tuple(tok.text for tok in doc)
        pos_tags = tuple(tok.pos_ for tok in doc)
        lemmas = tuple(tok.lemma_ for tok in doc)

        sentence_spans: list[tuple[int, int]] = []
        for sent in doc.sents:
            sentence_spans.append((sent.start_char, sent.end_char))

        entities: list[EntityMention] = []
        for ent in doc.ents:
            entities.append(EntityMention(
                text=ent.text,
                kind=ent.label_.lower(),
                start_char=ent.start_char,
                end_char=ent.end_char,
                confidence=1.0,
                source="spacy",
            ))

        return BaseParse(
            tokens=tokens,
            pos_tags=pos_tags,
            lemmas=lemmas,
            sentence_spans=tuple(sentence_spans),
            entities=tuple(entities),
        )
