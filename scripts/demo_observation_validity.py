import json
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

from ml.mobility_profile import MobilityProfile
from ml.pipeline import apply_profile


def main():
    source = Path("artifacts/pipeline-evaluation/mobility-engine-v1/results.json")
    cached = next(row for row in json.loads(source.read_text(encoding="utf-8"))
                  if row["filename"] == "curb_ramp/gsv-amsterdam-18384-CurbRamp.png")
    # A captura real não foi datada no dataset: os horários abaixo são exclusivamente simulados.
    scene = {key: cached[key] for key in ("image_path", "features", "predictions", "not_modeled", "inactive_features")}
    scene["observation"] = {"source": "demo_simulated_timestamp_on_recorded_predictions",
                            "observed_at": "2026-11-26T10:00:00+00:00"}
    profiles = {"regular_only": MobilityProfile("adequate", "regular_only", "minor", True),
                "minor_problems": MobilityProfile("adequate", "minor_problems", "minor", True)}
    results = []
    for moment in (datetime(2026, 11, 26, 11, tzinfo=timezone.utc), datetime(2026, 11, 27, 11, tzinfo=timezone.utc)):
        for name, profile in profiles.items():
            results.append({"scenario": name, **apply_profile(scene, profile, evaluated_at=moment, validity_period=timedelta(hours=24))})
    payload = {"source_predictions": str(source), "timestamps_simulated": True,
               "note": "Previsões reais já registradas; horários hipotéticos de demonstração, não datas reais de captura.",
               "profiles": {name: asdict(profile) for name, profile in profiles.items()}, "results": results}
    output = Path("artifacts/pipeline-evaluation/temporal-validity-demo")
    output.mkdir(parents=True, exist_ok=True)
    (output / "results.json").write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    for result in results:
        print(result["scenario"], result["observation"]["evaluated_at"], result["classification"], [r["message"] for r in result["reasons"]])


if __name__ == "__main__":
    main()
