from pipeline.verifier import quote_found, verify


def test_exact_and_fuzzy():
    t = "Проведение ежегодной инвентаризации складских запасов Общества."
    assert quote_found("ежегодной инвентаризации складских запасов", t)
    assert quote_found("ежегодной инвентаризации складских  запасов", t)
    assert not quote_found("ведение реестра договоров", t)


def test_verify_rejects_hallucination():
    chunks = [{"chunk_id": "x", "doc_name": "a.docx", "side": "before", "page": None, "clause": "3.1",
               "section": "3. Функции", "text": "Ведение единого реестра договоров Общества."}]
    good = {"type": "loss", "evidence": [{"doc_name": "a.docx", "side": "before", "clause": "3.1",
                                          "quote": "единого реестра договоров"}]}
    bad = {"type": "loss", "evidence": [{"doc_name": "a.docx", "side": "before", "clause": "3.1",
                                         "quote": "утверждение бюджета"}]}
    ok, rej = verify([good, bad], chunks, log=lambda *_: None)
    assert len(ok) == 1 and len(rej) == 1
