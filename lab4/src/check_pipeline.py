"""Проверки DVC из методички. Исходный CSV восстанавливается в finally."""
import json
from pathlib import Path
import subprocess
import sys

import pandas as pd


def repro():
    return subprocess.run([sys.executable, "-m", "src.run_dvc", "repro"],
                          text=True, encoding="utf-8", errors="replace", capture_output=True)


def run_id():
    return json.loads(Path("data/processed/mlflow_run.json").read_text(encoding="utf-8"))["run_id"]


def main():
    raw_path = Path("data/raw/tickets.csv")
    original = raw_path.read_bytes()
    results, logs = {}, []
    try:
        initial = repro()
        logs.append("INITIAL\n" + initial.stdout + initial.stderr)
        if initial.returncode:
            raise RuntimeError("Не удалось выполнить исходный конвейер")
        first_id = run_id()
        unchanged = repro()
        logs.append("UNCHANGED\n" + unchanged.stdout + unchanged.stderr)
        assert unchanged.returncode == 0 and run_id() == first_id
        results["unchanged_data_skips_stage"] = True
        frame = pd.read_csv(raw_path)
        frame.loc[0, "text"] += " уточнение"
        frame.to_csv(raw_path, index=False, lineterminator="\n")
        changed = repro()
        logs.append("CHANGED\n" + changed.stdout + changed.stderr)
        assert changed.returncode == 0 and run_id() != first_id
        results["changed_csv_reruns_stage"] = True
        frame.loc[0, "category"] = "INVALID"
        frame.to_csv(raw_path, index=False, lineterminator="\n")
        invalid = repro()
        logs.append("INVALID\n" + invalid.stdout + invalid.stderr)
        assert invalid.returncode != 0
        assert "category" in invalid.stdout + invalid.stderr
        results["invalid_category_blocks_pipeline"] = True
    finally:
        raw_path.write_bytes(original)
        restored = repro()
        logs.append("RESTORED\n" + restored.stdout + restored.stderr)
        if restored.returncode:
            raise RuntimeError("CSV восстановлен, но повторный запуск завершился ошибкой")
    # После восстановления DVC мог взять результаты из кэша. Проверяем актуальность.
    final = repro()
    logs.append("FINAL\n" + final.stdout + final.stderr)
    assert final.returncode == 0
    Path("docs").mkdir(exist_ok=True)
    Path("docs/check_results.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    Path("docs/dvc_checks.txt").write_text("\n\n".join(logs), encoding="utf-8")
    print(json.dumps(results, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
