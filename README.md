# Pactmill Labs

Public, synthetic demos for **contract-native, agent-ready data products**.

Skills & consulting method: [pactmill/skills](https://github.com/pactmill/skills).

## Lab: hello-contract

Compile a sample ODCS (+ ODPS) into JSON Schema, expectation-style checks, a freshness monitor stub, and an MCP tool descriptor. Detect breaking schema changes.

### Setup

```bash
pip install -r requirements.txt   # PyYAML
```

### Compile

```bash
PYTHONPATH=. python3 -m hello_contract compile \
  --odcs fixtures/customer_order_facts.odcs.yaml \
  --odps fixtures/customer_order_facts.odps.yaml \
  --out out/
```

### Breaking change (expect exit 1)

```bash
PYTHONPATH=. python3 -m hello_contract check-breaking \
  --before fixtures/customer_order_facts.odcs.yaml \
  --after fixtures/customer_order_facts.breaking.odcs.yaml
```

Fixtures are synthetic e-commerce order facts — no client data.

### Note

This is a thin educational spike. Production path should prefer [datacontract-cli](https://cli.datacontract.com/) for lint/export and layer Pactmill readiness/MCP policy on top.
