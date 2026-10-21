This adapter adds the exact retained native admission/recovery lineage checks
before the original terminal raw/statistical review. It does not modify any
measurement, preflight, guard, raw-workflow auditor or statistical function.

After root confirms the fixed native phase terminal and collects it with the
existing transport adapter into `work/inheritance-measurement/collections/native`,
run this reviewed wrapper in a new output directory:

```
taskset -c 8 /usr/bin/python3 -I -B work/inheritance-native-review/review.py \
  --source-freeze-sha256 NATIVE_REVIEW_SOURCE_FREEZE_SHA \
  --native-transfer-manifest-sha256 COLLECTED_NATIVE_MANIFEST_SHA \
  --ir-review work/inheritance-raw-review/ir-transport-closed/review.json \
  --output work/inheritance-raw-review/native-admission-closed \
  --analyze-after-terminal
```

The first receipt is `native-admission-lineage.json`: it joins the complete
original capture, its zero-work boundary, the reviewed recovery source/request,
successful transport, both metadata moves, all retained remote history bytes,
all three preserved local launch files, the replay approval and unchanged original
driver/launcher to the final native capture. It opaque-hashes all final captured
files and all 500 accepted IR files. It does not inspect native effects.

Only then does the byte-identical frozen transport reviewer run in `phase/`.
That original reviewer validates both fixed native workflows completely before
reproducing their prescribed statistics. The wrapper rechecks the admission
lineage afterward and writes `review-binding.json`. All three receipts and the
original `phase/review.json` are required for final evidence packaging. A valid
negative native phase remains negative; the wrapper does not change acceptance.

The prior IR transport-255 record remains intact. This wrapper does not normalize
any transport error or authorize another execution. It requires the completed
native replay's actual successful launch receipt; a different terminal failure
must be retained and reviewed separately. No host access or workload call exists
in this adapter.
