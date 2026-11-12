"""Unit tests validating Kubernetes manifests in deploy/kubernetes/."""

from pathlib import Path
import yaml
import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
K8S_DIR = REPO_ROOT / "deploy" / "kubernetes"


def test_all_yaml_manifests_parse_cleanly():
    yaml_files = list(K8S_DIR.glob("*.yaml"))
    assert len(yaml_files) >= 4, f"Expected at least 4 manifests, found {len(yaml_files)}"
    for f in yaml_files:
        docs = list(yaml.safe_load_all(f.read_text(encoding="utf-8")))
        assert len(docs) >= 1, f"Empty manifest file: {f.name}"
        for doc in docs:
            assert isinstance(doc, dict), f"Document in {f.name} is not a dict"
            assert "apiVersion" in doc and "kind" in doc and "metadata" in doc


def test_crd_schema_structure():
    crd_file = K8S_DIR / "crd-autoimmune-repair.yaml"
    crd = yaml.safe_load(crd_file.read_text(encoding="utf-8"))
    assert crd["kind"] == "CustomResourceDefinition"
    assert crd["spec"]["group"] == "autoimmune.io"
    assert crd["spec"]["names"]["kind"] == "AutoImmuneIncident"


def test_airgapped_networkpolicy_has_empty_egress():
    netpol_file = K8S_DIR / "networkpolicy.yaml"
    docs = list(yaml.safe_load_all(netpol_file.read_text(encoding="utf-8")))
    airgap = next(d for d in docs if d["metadata"]["name"] == "airgapped-sandbox-egress")
    assert airgap["spec"]["egress"] == [], "Sandbox egress must be strictly empty array for air-gapped isolation"


def test_rollout_security_context_hardened():
    rollout_file = K8S_DIR / "canary-rollout.yaml"
    docs = list(yaml.safe_load_all(rollout_file.read_text(encoding="utf-8")))
    rollout = next(d for d in docs if d["kind"] == "Rollout")
    pod_spec = rollout["spec"]["template"]["spec"]
    assert pod_spec["securityContext"]["runAsNonRoot"] is True
    container_sec = pod_spec["containers"][0]["securityContext"]
    assert container_sec["readOnlyRootFilesystem"] is True
    assert container_sec["allowPrivilegeEscalation"] is False
    assert "ALL" in container_sec["capabilities"]["drop"]
