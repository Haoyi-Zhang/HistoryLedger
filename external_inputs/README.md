# External input provenance

## Normalized noVNC history layer

`../data/public_windows.json` was supplied as a normalized derivative of public noVNC history. Its retained record says that extraction traversed the first 2,141 non-merge records oldest first, omitted the outer five percent, evaluated an evenly spaced interior grid, and retained forty eligible eight-commit windows. The extractor first removed individual file diffs with unrecognized code extensions or more than 4,000 raw changed lines; removing a file did not itself reject its window. It then required at least two aliases with retained files and 8–120 retained commit–file entries (not distinct paths), and finally at least eight positive structural events from at least two origins. These stages describe the supplied extractor; the normalized derivative does not permit replay of the historical selection.

The file contains numeric events, pseudonymous actor/entity labels, and bounded history structure. It contains no upstream source snapshots, paths, object identifiers, messages, timestamps, names, or email addresses. noVNC identifies its core JavaScript library as Mozilla Public License 2.0 and other file classes under separate notices; no noVNC source is redistributed here.

The normalized input is sufficient to reproduce the normalized-history calculations. It is not sufficient to audit the historical extraction. An optional local-checkout command is:

```sh
PYTHONPATH=src python -m rivet.extract_public   /path/to/noVNC /tmp/public_windows.json   --source-commit-count 2141 --window-size 8 --desired 40
```

A future checkout can differ in reachable history or traversal order. Matching retained numerical outputs does not prove that this optional reconstruction succeeds.

## Exact synthetic source controls

`source_cases.json` and `source_case_manifest.csv` retain eight original fixtures, each with at most three states and 512 UTF-8 bytes per state. They include two identical-endpoint path comparisons, whitespace and comment controls, a detected numeric change, and three explicit behavior distinctions missed by the token proxy. The fixture programs are never executed. These controls support falsification and boundary arguments, not public-repository breadth.

## Public patch boundary corpus

`public_patch_cases.json` retains twelve exact header-free unified patch fragments from twelve public MIT-licensed repositories. `public_patch_manifest.csv` records neutral case label, repository, stable repository URL, declared license, upstream license-file path, project-specific copyright notice, language, control status, file count, and included input. `THIRD_PARTY_NOTICES.md` preserves all thirteen project-specific copyright lines together with the common MIT grant and disclaimer; the executable checks refuse missing or inconsistent notice metadata.

The corpus was frozen as a bounded convenience sample with five language strata: Python, JavaScript, TypeScript, Rust, and C++. Each case contains one to three production-code files; no file patch exceeds 4,096 UTF-8 bytes and the whole retained corpus is below 32,768 bytes. One JavaScript comment correction is the negative control. The experiment executes no upstream code and retains no commit identifier, author identity, message, timestamp, branch, or full repository history.

The corpus supports one narrow source-to-event result: when the retained initial and final hunk states are supplied once to the deterministic extractor, the endpoint event surface is independent of how an analyst later spells a split, squash, or reorder path between those same retained endpoints. It also shows that path-additive alternatives are not generally invariant: the frozen results contain 3 hunk-path mismatches, 3 contiguous-block mismatches, 8 delete-then-add mismatches, and 11 positive edit/reverse cycles among 11 positive endpoint cases. These frequencies describe only the twelve retained cases.

## Derivation status

The noVNC normalized history still has an unresolved source-preimage gap. The public patch corpus closes a different obligation: it supplies lawful exact source fragments and a declared endpoint-anchored extraction relation for a discriminating multi-repository boundary campaign. It does not retroactively turn the noVNC windows into source-replay evidence, reproduce a forty-repository ranking study, or establish semantic completeness. The scientific lock therefore treats endpoint anchoring as a narrow representation principle and retains the stronger source-semantic claims as rejected.
