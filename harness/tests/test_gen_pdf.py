import gen_pdf


def test_dependencias_presentes_genera_pdf(tmp_path):
    md = tmp_path / "mini.md"
    md.write_text(
        "# Título\n\n| A | B |\n|---|---|\n| 1 | 2 |\n\n```bash\nexit=0\n```\n",
        encoding="utf-8",
    )
    rc = gen_pdf.main([str(md)])
    assert rc == 0
    pdf = md.with_suffix(".pdf")
    assert pdf.exists() and pdf.stat().st_size > 500


def test_entrada_inexistente_devuelve_66(tmp_path, capsys):
    rc = gen_pdf.main([str(tmp_path / "no.md")])
    assert rc == 66
    assert "No existe" in capsys.readouterr().err
