#!/usr/bin/env python3
"""Validate a sequential-schedule YAML against ErsatzTV's own JSON schema.

Worth doing before every deploy, and especially before this one. From 25.4 the
schedule is validated against a schema where every object is
additionalProperties:false, and SequentialPlayoutBuilder returns None on a
failed validation — the playout does not build AT ALL. The failure is close to
invisible: the items already built keep airing until they run out, and only
then does the channel drop to fallback colour bars, hours later and looking
like something else entirely.

Usage: validate-schedule.py <schedule.yml> <schema.json>
"""

import json
import sys

import yaml
from jsonschema import Draft202012Validator


def main(sched_path, schema_path):
    with open(sched_path) as f:
        doc = yaml.safe_load(f)
    with open(schema_path) as f:
        schema = json.load(f)

    v = Draft202012Validator(schema)
    errors = sorted(v.iter_errors(doc), key=lambda e: list(e.absolute_path))
    if not errors:
        n_content = len(doc.get("content", []))
        n_play = len(doc.get("playout", []))
        print("VALID — %d content keys, %d playout instructions"
              % (n_content, n_play))
        kinds = {}
        for ins in doc.get("playout", []):
            for k in ins:
                if k not in ("content", "custom_title", "tomorrow", "trim",
                             "discard_attempts", "fallback"):
                    kinds[k] = kinds.get(k, 0) + 1
                    break
        print("instructions: " + ", ".join("%s=%d" % kv
                                           for kv in sorted(kinds.items())))
        return 0

    print("INVALID — %d errors" % len(errors))
    for e in errors[:15]:
        path = "/".join(str(p) for p in e.absolute_path) or "<root>"
        print("  at %s: %s" % (path, e.message[:300]))
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1], sys.argv[2]))
