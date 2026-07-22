from job_intelligence.collectors.schema_org import _salary


def test_max_only_salary_does_not_render_none() -> None:
    result = _salary(
        {
            "currency": "USD",
            "value": {"maxValue": 150000, "unitText": "YEAR"},
        }
    )
    assert result == "USD 150000 per YEAR"
    assert "None" not in result
