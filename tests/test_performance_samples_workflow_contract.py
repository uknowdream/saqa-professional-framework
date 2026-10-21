from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github/workflows/saqa-performance-samples.yml"


def test_each_performance_sample_uses_a_fresh_digest_pinned_target():
    workflow = WORKFLOW.read_text(encoding="utf-8")
    assert 'TRAINING_IMAGE: "bkimminich/juice-shop@sha256:' in workflow
    assert "docker rm --force saqa-juice-shop-samples" in workflow
    assert workflow.index("docker rm --force saqa-juice-shop-samples") < workflow.index('docker run --detach --rm --name saqa-juice-shop-samples')
    assert "for run in 1 2 3 4 5; do" in workflow
    assert 'curl --fail --silent --show-error --max-time 5 http://127.0.0.1:3000/' in workflow
    assert "Give each sample a fresh application process" in workflow


def test_performance_samples_never_auto_promote_a_candidate_to_baseline():
    workflow = WORKFLOW.read_text(encoding="utf-8")
    assert "never auto-promoted to a baseline" in workflow
    assert "--output artifacts/performance/measured-run-set.json" in workflow
    assert "performance/baselines/juice-shop-local-v1.json" in workflow
