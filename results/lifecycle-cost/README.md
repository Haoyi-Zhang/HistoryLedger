# Lifecycle observations

`campaign.json` is the complete identity-bound fixed campaign: 16 native CPython
processes, 24 passes and 9,600 rewrite pairs. It retains every whole-process
counter, phase, cache state, host snapshot, raw signed pair and availability
field. `summary.csv` reports the four-child medians separately for each arm and
condition. Paid reuse charges both passes.

`predeclared-protocol.json` matches the source protocol in
`scripts/lifecycle-cost/`. All 24 uncompressed bundle streams are byte-identical;
`common-bundles.jsonl.gz` stores one lossless copy and `bundle-index.json` records
the exact bytes, multiplicity and all retained per-pass observations. Compression
is archival post-processing; each measured pass wrote the full 3,076,040 bytes.

These data concern the retained normalized events and shared receiver. They do
not supply original source snapshots, independently assessed identities or a
native deployment cohort. Reproduction instructions and measurement definitions
are in the accompanying script directory.
